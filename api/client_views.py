import calendar
import logging
import uuid
from datetime import date, timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from .forms import AgregarCarroForm, ItemCarroForm, MaquinariaForm, UnidadFlotaForm
from .models import (
    CarroArriendo, Contrato, ItemCarro, ItemContrato, Maquinaria, PagoWebpay, PerfilUsuario, UnidadFlota,
    fin_bloqueo,
)
from .payments import obtener_transaccion_webpay, respuesta_autorizada, respuesta_segura
from .permissions import tiene_rol
from .services import cambiar_estado_contrato, crear_contrato


logger = logging.getLogger(__name__)


# ==========================================================
# AUTORIZACIÓN DE VISTAS HTML POR ROL
# Reutiliza la misma comprobación de roles que la API y evita
# exponer carro de Empresa o panel Ejecutivo a otro perfil.
# ==========================================================
def rol_requerido(rol):
    def decorador(vista):
        @login_required
        @wraps(vista)
        def protegida(request, *args, **kwargs):
            if not tiene_rol(request.user, rol):
                return HttpResponseForbidden('No tienes permisos para acceder a esta sección.')
            return vista(request, *args, **kwargs)
        return protegida
    return decorador


# ==========================================================
# CATÁLOGO WEB
# Aplica búsqueda y categoría sobre maquinaria activa; agregar
# al carro no exige fechas ni crea una reserva.
# ==========================================================
def index_view(request):
    consulta = Maquinaria.objects.filter(activo=True)
    texto = request.GET.get('q', '').strip()
    categoria = request.GET.get('categoria', '').strip()
    if texto:
        consulta = consulta.filter(Q(nombre__icontains=texto) | Q(descripcion__icontains=texto) | Q(categoria__icontains=texto))
    if categoria:
        consulta = consulta.filter(categoria=categoria)
    return render(request, 'index.html', {
        'maquinarias': consulta, 'categorias': Maquinaria.objects.filter(activo=True).values_list('categoria', flat=True).distinct(),
        'q': texto, 'categoria_activa': categoria,
    })


@rol_requerido(PerfilUsuario.EMPRESA)
def carro_view(request):
    carro, _ = CarroArriendo.objects.get_or_create(usuario=request.user)
    hoy = timezone.localdate()
    try:
        anio, mes = map(int, request.GET.get('mes', '').split('-'))
        primer_dia = date(anio, mes, 1)
    except (TypeError, ValueError):
        primer_dia = hoy.replace(day=1)
    siguiente_mes = (primer_dia.replace(day=28) + timedelta(days=4)).replace(day=1)
    mes_anterior = (primer_dia - timedelta(days=1)).replace(day=1)

    items = list(carro.items.select_related('maquinaria').prefetch_related('maquinaria__unidades'))
    maquinaria_ids = [item.maquinaria_id for item in items]
    reservas = list(ItemContrato.objects.filter(
        maquinaria_id__in=maquinaria_ids,
        contrato__estado__in=(Contrato.PAGADO, Contrato.ENTREGADO),
        fecha_inicio__lt=siguiente_mes + timedelta(days=2),
        fecha_fin__gte=mes_anterior,
    ))

    # Calendario por ítem: un día solo figura disponible si alcanza para la cantidad solicitada.
    for item in items:
        reservas_maquina = [reserva for reserva in reservas if reserva.maquinaria_id == item.maquinaria_id]
        no_operativas = sum(1 for unidad in item.maquinaria.unidades.all() if unidad.estado != UnidadFlota.DISPONIBLE)
        semanas = []
        for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(primer_dia.year, primer_dia.month):
            dias = []
            for dia in semana:
                arrendadas = sum(
                    reserva.cantidad for reserva in reservas_maquina
                    if reserva.fecha_inicio <= dia < reserva.fecha_fin
                )
                entregas = sum(reserva.cantidad for reserva in reservas_maquina if reserva.fecha_fin == dia)
                mantenimiento = sum(
                    reserva.cantidad for reserva in reservas_maquina
                    if reserva.fecha_fin < dia < fin_bloqueo(reserva.fecha_fin)
                )
                bloqueadas = sum(
                    reserva.cantidad for reserva in reservas_maquina
                    if reserva.fecha_inicio <= dia < fin_bloqueo(reserva.fecha_fin)
                )
                libres = max(0, item.maquinaria.cantidad - no_operativas - bloqueadas)
                dias.append({
                    'fecha': dia, 'es_mes': dia.month == primer_dia.month, 'es_hoy': dia == hoy,
                    'arrendadas': arrendadas, 'entregas': entregas, 'mantenimiento': mantenimiento,
                    'libres': libres,
                    # Fechas pasadas y el día actual nunca se pueden solicitar.
                    'no_disponible': dia <= hoy or libres < item.cantidad,
                })
            semanas.append(dias)
        item.calendario_semanas = semanas

    return render(request, 'carro.html', {
        'carro': carro, 'items_carro': items, 'calendario_mes': primer_dia,
        'fecha_minima': hoy + timedelta(days=1),
        'mes_anterior': mes_anterior.strftime('%Y-%m'), 'mes_siguiente': siguiente_mes.strftime('%Y-%m'),
    })


@require_POST
@rol_requerido(PerfilUsuario.EMPRESA)
def agregar_carro(request, pk):
    maquinaria = get_object_or_404(Maquinaria, pk=pk, activo=True)
    form = AgregarCarroForm(request.POST)
    if form.is_valid() and form.cleaned_data['cantidad'] <= maquinaria.cantidad:
        carro, _ = CarroArriendo.objects.get_or_create(usuario=request.user)
        item, creado = ItemCarro.objects.get_or_create(
            carro=carro, maquinaria=maquinaria, defaults={'cantidad': form.cleaned_data['cantidad']},
        )
        if not creado:
            nueva_cantidad = item.cantidad + form.cleaned_data['cantidad']
            if nueva_cantidad > maquinaria.cantidad:
                messages.error(request, 'La cantidad total supera las unidades de la flota.')
                return redirect('home')
            item.cantidad = nueva_cantidad
            item.save(update_fields=('cantidad',))
        messages.success(request, f'{maquinaria.nombre} se agregó al carro.')
    else:
        messages.error(request, 'La cantidad indicada no es válida.')
    return redirect('home')


# ==========================================================
# EDICIÓN PERSISTENTE DEL CARRO
# Guarda cantidad y fechas en PostgreSQL mediante ModelForm; el
# cálculo mostrado proviene de las propiedades del modelo.
# ==========================================================
@require_POST
@rol_requerido(PerfilUsuario.EMPRESA)
def actualizar_item_carro(request, pk):
    item = get_object_or_404(ItemCarro, pk=pk, carro__usuario=request.user)
    form = ItemCarroForm(request.POST, instance=item)
    if form.is_valid() and form.cleaned_data['cantidad'] <= item.maquinaria.cantidad:
        form.save()
        messages.success(request, f'{item.maquinaria.nombre}: período y cantidad actualizados.')
    else:
        detalle = ' '.join(error for errores in form.errors.values() for error in errores)
        messages.error(request, detalle or 'La cantidad supera las unidades de la flota.')
    return redirect('carro_web')


@require_POST
@rol_requerido(PerfilUsuario.EMPRESA)
def eliminar_item_carro(request, pk):
    get_object_or_404(ItemCarro, pk=pk, carro__usuario=request.user).delete()
    messages.success(request, 'Ítem eliminado del carro.')
    return redirect('carro_web')


@require_POST
@rol_requerido(PerfilUsuario.EMPRESA)
def checkout_web(request):
    try:
        contrato = crear_contrato(request.user)
        messages.success(request, f'Contrato #{contrato.id} creado y pendiente de pago.')
        return redirect('mis_contratos_web')
    except (CarroArriendo.DoesNotExist, ValueError) as error:
        messages.error(request, str(error) or 'No existe un carro.')
        return redirect('carro_web')


@rol_requerido(PerfilUsuario.EMPRESA)
def mis_contratos_view(request):
    contratos = Contrato.objects.filter(usuario=request.user).select_related('pago_webpay').prefetch_related('items')
    return render(request, 'contratos.html', {
        'contratos': contratos,
        'webpay_integracion': settings.WEBPAY_ENVIRONMENT == 'integration',
    })


# ==========================================================
# PAGO WEBPAY PLUS
# Inicia la transacción en Transbank y confirma el resultado
# del retorno antes de cambiar el contrato a PAGADO.
# ==========================================================
@require_POST
@rol_requerido(PerfilUsuario.EMPRESA)
def webpay_iniciar_view(request, pk):
    contrato = get_object_or_404(Contrato, pk=pk, usuario=request.user)
    if contrato.estado != Contrato.PENDIENTE:
        messages.error(request, 'Solo los contratos pendientes se pueden pagar.')
        return redirect('mis_contratos_web')

    pago = PagoWebpay.objects.filter(contrato=contrato).first()
    if pago and pago.estado == PagoWebpay.INICIADO and pago.token and pago.url_pago:
        return render(request, 'webpay_redirect.html', {
            'pago': pago, 'webpay_integracion': settings.WEBPAY_ENVIRONMENT == 'integration',
        })
    if pago and pago.estado == PagoWebpay.ERROR and pago.token:
        messages.error(request, 'El resultado del pago anterior requiere revisión antes de volver a intentar.')
        return redirect('mis_contratos_web')

    identificador = uuid.uuid4().hex[:12]
    buy_order = f'MR-{contrato.id}-{identificador}'[:26]
    session_id = f'contrato-{contrato.id}-usuario-{request.user.id}-{identificador}'[:61]
    if pago:
        pago.buy_order = buy_order
        pago.session_id = session_id
        pago.monto = contrato.total
        pago.token = None
        pago.url_pago = ''
        pago.estado = PagoWebpay.INICIADO
        pago.response_code = None
        pago.authorization_code = ''
        pago.payment_type_code = ''
        pago.card_last4 = ''
        pago.respuesta = {}
        pago.save()
    else:
        pago = PagoWebpay.objects.create(
            contrato=contrato,
            buy_order=buy_order,
            session_id=session_id,
            monto=contrato.total,
        )

    try:
        respuesta = obtener_transaccion_webpay().create(
            pago.buy_order,
            pago.session_id,
            int(pago.monto),
            request.build_absolute_uri(reverse('webpay_retorno')),
        )
        pago.token = respuesta['token']
        pago.url_pago = respuesta['url']
        pago.save(update_fields=('token', 'url_pago', 'actualizado_en'))
    except Exception as error:  # El SDK encapsula errores HTTP y de validación en varias clases.
        logger.exception('No fue posible iniciar Webpay para el contrato %s', contrato.id)
        pago.estado = PagoWebpay.ERROR
        pago.respuesta = {'error': str(error)[:500]}
        pago.save(update_fields=('estado', 'respuesta', 'actualizado_en'))
        messages.error(request, 'Webpay no está disponible en este momento. Intenta nuevamente.')
        return redirect('mis_contratos_web')

    return render(request, 'webpay_redirect.html', {
        'pago': pago, 'webpay_integracion': settings.WEBPAY_ENVIRONMENT == 'integration',
    })


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def webpay_retorno_view(request):
    datos = request.POST if request.method == 'POST' else request.GET
    token = datos.get('token_ws')

    # Webpay retorna TBK_TOKEN, sin token_ws, cuando la persona aborta el flujo.
    if not token:
        token_abortado = datos.get('TBK_TOKEN')
        pago = (
            PagoWebpay.objects.filter(token=token_abortado).select_related('contrato').first()
            if token_abortado else None
        )
        if pago and pago.estado == PagoWebpay.INICIADO:
            pago.estado = PagoWebpay.ANULADO
            pago.save(update_fields=('estado', 'actualizado_en'))
        return render(request, 'webpay_resultado.html', {
            'pago': pago,
            'exito': False,
            'detalle': 'El pago fue anulado antes de completarse.',
        })

    pago = PagoWebpay.objects.filter(token=token).select_related('contrato').first()
    if not pago:
        return render(request, 'webpay_resultado.html', {
            'exito': False,
            'detalle': 'No se encontró una solicitud de pago asociada a este retorno.',
        }, status=400)
    if pago.estado != PagoWebpay.INICIADO:
        return render(request, 'webpay_resultado.html', {
            'pago': pago,
            'exito': pago.estado == PagoWebpay.AUTORIZADO,
            'detalle': 'Este resultado de pago ya fue procesado.',
        })

    try:
        cliente_webpay = obtener_transaccion_webpay()
        respuesta = cliente_webpay.commit(token)
    except Exception as error:
        # Si el commit alcanzó a procesarse pero su respuesta se perdió, status
        # evita crear luego una segunda transacción para el mismo contrato.
        logger.exception('Falló commit de Webpay para la orden %s; se consultará su estado', pago.buy_order)
        try:
            respuesta = cliente_webpay.status(token)
        except Exception:
            logger.exception('Tampoco fue posible consultar el estado de %s', pago.buy_order)
            pago.estado = PagoWebpay.ERROR
            pago.respuesta = {'error': str(error)[:500]}
            pago.save(update_fields=('estado', 'respuesta', 'actualizado_en'))
            return render(request, 'webpay_resultado.html', {
                'pago': pago,
                'exito': False,
                'detalle': 'No fue posible confirmar la respuesta de Webpay. El pago requiere revisión.',
            }, status=502)

    pago.respuesta = respuesta_segura(respuesta)
    pago.response_code = respuesta.get('response_code')
    pago.authorization_code = respuesta.get('authorization_code') or ''
    pago.payment_type_code = respuesta.get('payment_type_code') or ''
    tarjeta = respuesta.get('card_detail') or {}
    pago.card_last4 = str(tarjeta.get('card_number') or '')[-4:]

    if not respuesta_autorizada(respuesta, pago):
        pago.estado = PagoWebpay.RECHAZADO
        pago.save()
        return render(request, 'webpay_resultado.html', {
            'pago': pago,
            'exito': False,
            'detalle': 'La transacción fue rechazada o sus datos no coinciden con la reserva.',
        })

    try:
        with transaction.atomic():
            cambiar_estado_contrato(pago.contrato_id, Contrato.PAGADO)
            pago.estado = PagoWebpay.AUTORIZADO
            pago.save()
    except (Contrato.DoesNotExist, ValueError) as error:
        # Si la flota dejó de estar disponible durante el flujo externo, se
        # revierte el cargo para no cobrar una reserva imposible de cumplir.
        try:
            cliente_webpay.refund(token, int(pago.monto))
            pago.estado = PagoWebpay.REEMBOLSADO
            detalle = f'El pago fue reembolsado porque no se pudo confirmar la reserva: {error}'
        except Exception:
            logger.exception('Pago autorizado sin reserva; además falló el reembolso de %s', pago.buy_order)
            pago.estado = PagoWebpay.ERROR
            detalle = 'El pago fue autorizado, pero la reserva requiere revisión manual.'
        pago.save()
        return render(request, 'webpay_resultado.html', {
            'pago': pago, 'exito': False, 'detalle': detalle,
        }, status=409)

    return render(request, 'webpay_resultado.html', {
        'pago': pago,
        'exito': True,
        'detalle': 'Pago autorizado. La maquinaria quedó reservada correctamente.',
    })


# ==========================================================
# PANEL WEB DEL EJECUTIVO
# Ofrece CRUD de flota y avance de contratos sin Django Admin.
# También resume ocupación actual y mensual; las operaciones
# críticas delegan en los servicios de dominio.
# ==========================================================
@rol_requerido(PerfilUsuario.EJECUTIVO)
def panel_view(request):
    hoy = timezone.localdate()
    maquinarias = list(Maquinaria.objects.prefetch_related('unidades').all())

    # Ocupación de hoy: solo PAGADO y ENTREGADO representan arriendos activos.
    ocupacion_hoy = dict(
        ItemContrato.objects.filter(
            maquinaria_id__isnull=False,
            contrato__estado__in=(Contrato.PAGADO, Contrato.ENTREGADO),
            fecha_inicio__lte=hoy,
            fecha_fin__gt=hoy,
        ).values_list('maquinaria_id').annotate(total=Sum('cantidad'))
    )
    for maquinaria in maquinarias:
        maquinaria.arrendadas_hoy = ocupacion_hoy.get(maquinaria.id, 0)
        maquinaria.reservadas = maquinaria.unidades_reservadas_activas
        maquinaria.no_operativas = sum(1 for unidad in maquinaria.unidades.all() if unidad.estado != UnidadFlota.DISPONIBLE)
        maquinaria.disponibles_hoy = max(
            0, maquinaria.cantidad - maquinaria.arrendadas_hoy - maquinaria.no_operativas
        )
        maquinaria.disponibles_globales = maquinaria.disponibles_sin_reserva

    # Calendario mensual navegable mediante ?mes=AAAA-MM.
    try:
        anio, mes = map(int, request.GET.get('mes', '').split('-'))
        primer_dia = date(anio, mes, 1)
    except (TypeError, ValueError):
        primer_dia = hoy.replace(day=1)
    siguiente_mes = (primer_dia.replace(day=28) + timedelta(days=4)).replace(day=1)
    mes_anterior = (primer_dia - timedelta(days=1)).replace(day=1)

    reservas_mes = list(ItemContrato.objects.filter(
        maquinaria_id__isnull=False,
        contrato__estado__in=(Contrato.PAGADO, Contrato.ENTREGADO),
        fecha_inicio__lt=siguiente_mes,
        fecha_fin__gt=primer_dia,
    ).select_related('maquinaria', 'contrato'))
    unidades_no_operativas = list(
        UnidadFlota.objects.exclude(estado=UnidadFlota.DISPONIBLE).select_related('maquinaria')
    )

    semanas = []
    for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(primer_dia.year, primer_dia.month):
        dias = []
        for dia in semana:
            eventos = []
            for item in reservas_mes:
                if item.fecha_inicio == dia:
                    eventos.append({'tipo': 'Inicio', 'clase': 'inicio', 'nombre': item.maquinaria_nombre, 'cantidad': item.cantidad})
                if item.fecha_fin == dia:
                    eventos.append({'tipo': 'Entrega', 'clase': 'entrega', 'nombre': item.maquinaria_nombre, 'cantidad': item.cantidad})
            if dia == hoy:
                for unidad in unidades_no_operativas:
                    eventos.append({
                        'tipo': unidad.get_estado_display(), 'clase': unidad.estado.lower(),
                        'nombre': f'{unidad.maquinaria.nombre} · {unidad.codigo}', 'cantidad': 1,
                    })
            dias.append({
                'fecha': dia,
                'es_mes': dia.month == primer_dia.month,
                'es_hoy': dia == hoy,
                'eventos': eventos,
                'detalle': ', '.join(f'{evento["tipo"]}: {evento["nombre"]} ({evento["cantidad"]})' for evento in eventos),
            })
        semanas.append(dias)

    return render(request, 'panel.html', {
        'maquinarias': maquinarias,
        'contratos': Contrato.objects.select_related('usuario').prefetch_related('items__unidades_asignadas').all(),
        'calendario_semanas': semanas,
        'calendario_mes': primer_dia,
        'mes_anterior': mes_anterior.strftime('%Y-%m'),
        'mes_siguiente': siguiente_mes.strftime('%Y-%m'),
        'hoy': hoy,
        'transiciones': {
            Contrato.PENDIENTE: (Contrato.PAGADO, Contrato.CANCELADO),
            Contrato.PAGADO: (Contrato.ENTREGADO, Contrato.CANCELADO),
            Contrato.ENTREGADO: (Contrato.COMPLETADO, Contrato.CANCELADO),
        },
    })


@rol_requerido(PerfilUsuario.EJECUTIVO)
def maquinaria_form_view(request, pk=None):
    maquinaria = get_object_or_404(Maquinaria, pk=pk) if pk else None
    form = MaquinariaForm(request.POST or None, instance=maquinaria)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Maquinaria guardada correctamente.')
        return redirect('panel')
    return render(request, 'maquinaria_form.html', {'form': form, 'maquinaria': maquinaria})


@require_POST
@rol_requerido(PerfilUsuario.EJECUTIVO)
def maquinaria_eliminar_view(request, pk):
    maquinaria = get_object_or_404(Maquinaria, pk=pk)
    maquinaria.delete()
    messages.success(request, 'Maquinaria eliminada.')
    return redirect('panel')


@require_POST
@rol_requerido(PerfilUsuario.EJECUTIVO)
def unidad_flota_actualizar_view(request, pk):
    unidad = get_object_or_404(UnidadFlota, pk=pk)
    form = UnidadFlotaForm(request.POST, instance=unidad)
    if form.is_valid():
        nuevo_estado = form.cleaned_data['estado']
        tiene_arriendo_activo = unidad.items_contrato.filter(
            contrato__estado__in=(Contrato.PAGADO, Contrato.ENTREGADO)
        ).exists()
        if nuevo_estado != UnidadFlota.DISPONIBLE and tiene_arriendo_activo:
            messages.error(request, f'{unidad.codigo} está asignada a un arriendo activo.')
        else:
            form.save()
            messages.success(request, f'{unidad.codigo} actualizada.')
    else:
        messages.error(request, 'No se pudo actualizar la unidad de flota.')
    return redirect(f'{reverse("panel")}#flota')


@require_POST
@rol_requerido(PerfilUsuario.EJECUTIVO)
def contrato_estado_view(request, pk):
    try:
        cambiar_estado_contrato(pk, request.POST.get('estado'))
        messages.success(request, 'Estado actualizado.')
    except (Contrato.DoesNotExist, ValueError) as error:
        messages.error(request, str(error) or 'Contrato no encontrado.')
    return redirect('panel')
