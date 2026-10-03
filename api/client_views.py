from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AgregarCarroForm, ItemCarroForm, MaquinariaForm
from .models import CarroArriendo, Contrato, ItemCarro, Maquinaria, PerfilUsuario
from .permissions import tiene_rol
from .services import cambiar_estado_contrato, crear_contrato


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
    return render(request, 'carro.html', {'carro': carro})


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
    contratos = Contrato.objects.filter(usuario=request.user).prefetch_related('items')
    return render(request, 'contratos.html', {'contratos': contratos})


# ==========================================================
# PANEL WEB DEL EJECUTIVO
# Ofrece CRUD de flota y avance de contratos sin Django Admin.
# Las operaciones críticas delegan en los servicios de dominio.
# ==========================================================
@rol_requerido(PerfilUsuario.EJECUTIVO)
def panel_view(request):
    return render(request, 'panel.html', {
        'maquinarias': Maquinaria.objects.all(),
        'contratos': Contrato.objects.select_related('usuario').prefetch_related('items').all(),
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
def contrato_estado_view(request, pk):
    try:
        cambiar_estado_contrato(pk, request.POST.get('estado'))
        messages.success(request, 'Estado actualizado.')
    except (Contrato.DoesNotExist, ValueError) as error:
        messages.error(request, str(error) or 'Contrato no encontrado.')
    return redirect('panel')
