from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    MARGEN_ENTRE_ARRIENDOS_DIAS, CarroArriendo, Contrato, ItemContrato, Maquinaria, fin_bloqueo,
    UnidadFlota,
)


# ==========================================================
# CHECKOUT TRANSACCIONAL
# Bloquea el carro, valida ítems y crea Contrato + histórico en
# una transacción: ante cualquier error no queda creación parcial.
# ==========================================================
@transaction.atomic
def crear_contrato(usuario):
    """Crea un contrato pendiente y copia precios/fechas para mantener el histórico."""
    carro = CarroArriendo.objects.select_for_update().get(usuario=usuario)
    items = list(carro.items.select_related('maquinaria'))
    if not items:
        raise ValueError('El carro está vacío.')

    # El carro acepta ítems sin período, pero el contrato nunca se crea con fechas incompletas.
    invalidos = [item.maquinaria.nombre for item in items if not item.fechas_validas]
    if invalidos:
        raise ValueError(f'Debes indicar fechas válidas para: {", ".join(invalidos)}.')
    inicios_invalidos = [item.maquinaria.nombre for item in items if item.fecha_inicio <= timezone.localdate()]
    if inicios_invalidos:
        raise ValueError(f'El arriendo debe comenzar desde mañana para: {", ".join(inicios_invalidos)}.')

    total = sum((item.subtotal for item in items), Decimal('0'))
    contrato = Contrato.objects.create(usuario=usuario, total=total)
    ItemContrato.objects.bulk_create([
        ItemContrato(
            contrato=contrato, maquinaria=item.maquinaria, maquinaria_nombre=item.maquinaria.nombre,
            cantidad=item.cantidad, fecha_inicio=item.fecha_inicio, fecha_fin=item.fecha_fin,
            tarifa_diaria=item.maquinaria.tarifa_diaria, tarifa_semanal=item.maquinaria.tarifa_semanal,
            garantia=item.maquinaria.garantia, subtotal=item.subtotal,
        ) for item in items
    ])
    carro.items.all().delete()
    return contrato


# ==========================================================
# MÁQUINA DE ESTADOS
# Solo permite el flujo definido y cancelación desde estados
# operativos; COMPLETADO y CANCELADO quedan como terminales.
# ==========================================================
TRANSICIONES = {
    Contrato.PENDIENTE: {Contrato.PAGADO, Contrato.CANCELADO},
    Contrato.PAGADO: {Contrato.ENTREGADO, Contrato.CANCELADO},
    Contrato.ENTREGADO: {Contrato.COMPLETADO, Contrato.CANCELADO},
    Contrato.COMPLETADO: set(),
    Contrato.CANCELADO: set(),
}


# ==========================================================
# PAGO, DISPONIBILIDAD Y BLOQUEO CONCURRENTE
# Al pagar bloquea contrato y filas de maquinaria, reúne reservas
# solapadas y rechaza la operación si la flota no alcanza.
# CANCELADO/COMPLETADO liberan unidades porque dejan de formar
# parte de los estados que unidades_reservadas considera activos.
# ==========================================================
@transaction.atomic
def cambiar_estado_contrato(contrato_id, nuevo_estado):
    """Bloquea contrato y flota al pagar; así dos pagos simultáneos no sobre-reservan."""
    contrato = Contrato.objects.select_for_update().get(pk=contrato_id)
    if nuevo_estado not in TRANSICIONES[contrato.estado]:
        raise ValueError(f'No se puede pasar de {contrato.estado} a {nuevo_estado}.')

    if nuevo_estado == Contrato.PAGADO:
        items = list(contrato.items.select_related('maquinaria'))
        ids = sorted({item.maquinaria_id for item in items if item.maquinaria_id})
        maquinarias = {m.id: m for m in Maquinaria.objects.select_for_update().filter(id__in=ids)}
        for maquinaria_id in ids:
            maquinaria = maquinarias.get(maquinaria_id)
            items_maquina = [item for item in items if item.maquinaria_id == maquinaria_id]
            if not maquinaria or not maquinaria.activo:
                raise ValueError(f'{items_maquina[0].maquinaria_nombre} ya no está disponible.')

            inicio = min(item.fecha_inicio for item in items_maquina)
            fin_bloqueado = max(fin_bloqueo(item.fecha_fin) for item in items_maquina)
            reservas = list(ItemContrato.objects.filter(
                maquinaria_id=maquinaria_id, contrato__estado__in=(Contrato.PAGADO, Contrato.ENTREGADO),
                fecha_inicio__lt=fin_bloqueado,
                # fin_bloqueo(reserva) > inicio, expresado sin funciones SQL.
                fecha_fin__gt=inicio - timedelta(days=MARGEN_ENTRE_ARRIENDOS_DIAS + 1),
            ).exclude(contrato_id=contrato.id).prefetch_related('unidades_asignadas'))
            no_operativas = maquinaria.unidades.exclude(estado=UnidadFlota.DISPONIBLE).count()

            # Se revisa cada punto donde cambia la ocupación, incluyendo ítems superpuestos del mismo contrato.
            puntos = {item.fecha_inicio for item in items_maquina}
            puntos.update(item.fecha_inicio for item in reservas)
            for punto in puntos:
                solicitadas = sum(i.cantidad for i in items_maquina if i.fecha_inicio <= punto < fin_bloqueo(i.fecha_fin))
                ocupadas = sum(i.cantidad for i in reservas if i.fecha_inicio <= punto < fin_bloqueo(i.fecha_fin))
                if solicitadas + ocupadas + no_operativas > maquinaria.cantidad:
                    libres = max(0, maquinaria.cantidad - ocupadas - no_operativas)
                    raise ValueError(
                        f'Solo hay {libres} unidad(es) de {maquinaria.nombre} disponibles para ese período, '
                        'considerando el día de mantención posterior a cada entrega.'
                    )

            # Asigna automáticamente IDs físicos disponibles a cada ítem confirmado.
            usadas_en_contrato = set()
            for item in items_maquina:
                reservas_solapadas = [
                    reserva for reserva in reservas
                    if reserva.fecha_inicio < fin_bloqueo(item.fecha_fin)
                    and fin_bloqueo(reserva.fecha_fin) > item.fecha_inicio
                ]
                ocupadas_ids = {
                    unidad.id for reserva in reservas_solapadas for unidad in reserva.unidades_asignadas.all()
                }
                candidatas = list(
                    UnidadFlota.objects.select_for_update().filter(
                        maquinaria=maquinaria, estado=UnidadFlota.DISPONIBLE,
                    ).exclude(id__in=ocupadas_ids | usadas_en_contrato).order_by('codigo')[:item.cantidad]
                )
                if len(candidatas) < item.cantidad:
                    raise ValueError(f'No hay IDs físicos suficientes disponibles para {maquinaria.nombre}.')
                item.unidades_asignadas.set(candidatas)
                usadas_en_contrato.update(unidad.id for unidad in candidatas)

    contrato.estado = nuevo_estado
    contrato.save(update_fields=('estado', 'actualizado_en'))
    return contrato
