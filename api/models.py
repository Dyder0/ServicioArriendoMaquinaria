from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


# Una entrega bloquea también el día siguiente para revisión y mantención.
MARGEN_ENTRE_ARRIENDOS_DIAS = 1


def fin_bloqueo(fecha_fin):
    """Devuelve el primer día en que el equipo puede volver a arrendarse."""
    return fecha_fin + timedelta(days=MARGEN_ENTRE_ARRIENDOS_DIAS + 1)


# ==========================================================
# ROLES DE USUARIO
# Extiende al usuario de Django mediante relación 1:1 sin
# sustituir el modelo de autenticación existente.
# ==========================================================
class PerfilUsuario(models.Model):
    EMPRESA = 'EMPRESA_CONSTRUCTORA'
    EJECUTIVO = 'EJECUTIVO_ARRIENDOS'
    ROLES = [(EMPRESA, 'Empresa constructora'), (EJECUTIVO, 'Ejecutivo de arriendos')]

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='perfil')
    rol = models.CharField(max_length=30, choices=ROLES, default=EMPRESA)

    def __str__(self):
        return f'{self.usuario.username} · {self.get_rol_display()}'


# ==========================================================
# FLOTA DE MAQUINARIA
# Mantiene datos comerciales, ambas tarifas y el total físico
# de unidades disponible para calcular ocupación por período.
# ==========================================================
class Maquinaria(models.Model):
    nombre = models.CharField(max_length=140)
    categoria = models.CharField(max_length=80, db_index=True)
    descripcion = models.TextField()
    image_url = models.URLField('URL de imagen', max_length=500, blank=True)
    tarifa_diaria = models.DecimalField(max_digits=12, decimal_places=0, validators=[MinValueValidator(0)])
    tarifa_semanal = models.DecimalField(max_digits=12, decimal_places=0, validators=[MinValueValidator(0)])
    garantia = models.DecimalField(max_digits=12, decimal_places=0, default=0, validators=[MinValueValidator(0)])
    cantidad = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    activo = models.BooleanField(default=True, db_index=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('nombre',)
        verbose_name = 'maquinaria'
        verbose_name_plural = 'maquinarias'

    def __str__(self):
        return self.nombre

    def unidades_reservadas(self, fecha_inicio, fecha_fin, excluir_contrato=None):
        """Suma reservas que se cruzan con [inicio, fin); pendientes no bloquean flota."""
        # Se extiende cada período hasta después del día de mantención posterior a la entrega.
        fin_solicitado_bloqueado = fin_bloqueo(fecha_fin)
        desplazamiento = timedelta(days=MARGEN_ENTRE_ARRIENDOS_DIAS + 1)
        consulta = self.items_contrato.filter(
            contrato__estado__in=(Contrato.PAGADO, Contrato.ENTREGADO),
            fecha_inicio__lt=fin_solicitado_bloqueado,
            fecha_fin__gt=fecha_inicio - desplazamiento,
        )
        if excluir_contrato:
            consulta = consulta.exclude(contrato_id=excluir_contrato)
        return consulta.aggregate(total=Sum('cantidad'))['total'] or 0

    def disponibilidad(self, fecha_inicio, fecha_fin, excluir_contrato=None):
        no_operativas = self.unidades.exclude(estado=UnidadFlota.DISPONIBLE).count()
        return max(0, self.cantidad - no_operativas - self.unidades_reservadas(fecha_inicio, fecha_fin, excluir_contrato))

    @property
    def unidades_reservadas_activas(self):
        """Unidades físicas asignadas actualmente a contratos PAGADO/ENTREGADO."""
        return self.unidades.filter(
            items_contrato__contrato__estado__in=(Contrato.PAGADO, Contrato.ENTREGADO)
        ).distinct().count()

    @property
    def disponibles_sin_reserva(self):
        """Flota operativa sin ninguna asignación activa, independiente del período."""
        return self.unidades.filter(estado=UnidadFlota.DISPONIBLE).exclude(
            items_contrato__contrato__estado__in=(Contrato.PAGADO, Contrato.ENTREGADO)
        ).distinct().count()


# ==========================================================
# UNIDADES FÍSICAS DE LA FLOTA
# Cada maquinaria posee equipos identificables. Su estado actual
# bloquea mantención/revisión y el permiso se gestiona por unidad.
# ==========================================================
class UnidadFlota(models.Model):
    DISPONIBLE = 'DISPONIBLE'
    MANTENIMIENTO = 'MANTENIMIENTO'
    REVISION = 'REVISION'
    ESTADOS = [
        (DISPONIBLE, 'Disponible'),
        (MANTENIMIENTO, 'Mantenimiento'),
        (REVISION, 'Revisión'),
    ]

    maquinaria = models.ForeignKey(Maquinaria, on_delete=models.CASCADE, related_name='unidades')
    codigo = models.CharField(max_length=30, unique=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=DISPONIBLE, db_index=True)
    permiso_circulacion = models.BooleanField(default=False)

    class Meta:
        ordering = ('codigo',)

    def __str__(self):
        return f'{self.codigo} · {self.maquinaria.nombre}'


# ==========================================================
# CARRO PERSISTENTE
# La relación OneToOne garantiza un único carro activo por
# usuario y PostgreSQL conserva sus ítems entre sesiones.
# ==========================================================
class CarroArriendo(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='carro_arriendo')
    actualizado_en = models.DateTimeField(auto_now=True)

    @property
    def total(self):
        return sum((item.subtotal for item in self.items.select_related('maquinaria')), Decimal('0'))

    @property
    def listo_checkout(self):
        items = list(self.items.all())
        return bool(items) and all(item.fechas_validas for item in items)

    def __str__(self):
        return f'Carro de {self.usuario.username}'


# ==========================================================
# ÍTEM DE ARRIENDO Y CÁLCULO DE PRECIO
# Las fechas son editables en el carro. El servidor calcula
# semanas completas, días restantes, garantía y subtotal.
# ==========================================================
class ItemCarro(models.Model):
    carro = models.ForeignKey(CarroArriendo, on_delete=models.CASCADE, related_name='items')
    maquinaria = models.ForeignKey(Maquinaria, on_delete=models.CASCADE, related_name='items_carro')
    cantidad = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    # Las fechas se completan en el carro, no al agregar desde el catálogo.
    fecha_inicio = models.DateField(blank=True, null=True)
    fecha_fin = models.DateField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=('carro', 'maquinaria'), name='item_carro_maquinaria_unico'),
            models.CheckConstraint(condition=Q(fecha_fin__gt=models.F('fecha_inicio')), name='item_carro_fechas_validas'),
        ]

    def clean(self):
        if self.fecha_inicio and self.fecha_inicio <= timezone.localdate():
            raise ValidationError({'fecha_inicio': 'El arriendo debe comenzar desde mañana.'})
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin <= self.fecha_inicio:
            raise ValidationError({'fecha_fin': 'La fecha de término debe ser posterior a la fecha de inicio.'})

    @property
    def dias(self):
        if not self.fecha_inicio or not self.fecha_fin or self.fecha_fin <= self.fecha_inicio:
            return 0
        return (self.fecha_fin - self.fecha_inicio).days

    @property
    def semanas(self):
        return self.dias // 7

    @property
    def dias_restantes(self):
        return self.dias % 7

    @property
    def fechas_validas(self):
        return bool(self.fecha_inicio and self.fecha_fin and self.fecha_fin > self.fecha_inicio)

    @property
    def subtotal_arriendo(self):
        if not self.fechas_validas:
            return Decimal('0')
        semanas, dias_restantes = divmod(self.dias, 7)
        valor_unitario = semanas * self.maquinaria.tarifa_semanal + dias_restantes * self.maquinaria.tarifa_diaria
        return valor_unitario * self.cantidad

    @property
    def subtotal(self):
        # La garantía se cobra una vez por cada unidad incluida en el ítem.
        if not self.fechas_validas:
            return Decimal('0')
        return self.subtotal_arriendo + self.maquinaria.garantia * self.cantidad

    @property
    def garantia_total(self):
        return self.maquinaria.garantia * self.cantidad


# ==========================================================
# CONTRATO Y ESTADOS DEL CICLO DE ARRIENDO
# Los CHOICES restringen el estado persistido; las transiciones
# de negocio se validan en services.py.
# ==========================================================
class Contrato(models.Model):
    PENDIENTE = 'PENDIENTE'
    PAGADO = 'PAGADO'
    ENTREGADO = 'ENTREGADO'
    COMPLETADO = 'COMPLETADO'
    CANCELADO = 'CANCELADO'
    ESTADOS = [(valor, valor.title()) for valor in (PENDIENTE, PAGADO, ENTREGADO, COMPLETADO, CANCELADO)]

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='contratos')
    estado = models.CharField(max_length=20, choices=ESTADOS, default=PENDIENTE, db_index=True)
    total = models.DecimalField(max_digits=14, decimal_places=0)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-creado_en',)

    def __str__(self):
        return f'Contrato #{self.pk} · {self.usuario.username}'


# ==========================================================
# PAGO WEBPAY PLUS
# Conserva la orden y el resultado necesarios para validar el
# retorno de Transbank sin guardar nunca el número de tarjeta.
# ==========================================================
class PagoWebpay(models.Model):
    INICIADO = 'INICIADO'
    AUTORIZADO = 'AUTORIZADO'
    RECHAZADO = 'RECHAZADO'
    ANULADO = 'ANULADO'
    REEMBOLSADO = 'REEMBOLSADO'
    ERROR = 'ERROR'
    ESTADOS = [
        (INICIADO, 'Iniciado'),
        (AUTORIZADO, 'Autorizado'),
        (RECHAZADO, 'Rechazado'),
        (ANULADO, 'Anulado por el usuario'),
        (REEMBOLSADO, 'Reembolsado'),
        (ERROR, 'Error'),
    ]

    contrato = models.OneToOneField(Contrato, on_delete=models.PROTECT, related_name='pago_webpay')
    buy_order = models.CharField(max_length=26, unique=True)
    session_id = models.CharField(max_length=61)
    monto = models.DecimalField(max_digits=14, decimal_places=0)
    token = models.CharField(max_length=64, unique=True, null=True, blank=True)
    url_pago = models.URLField(max_length=500, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=INICIADO, db_index=True)
    response_code = models.IntegerField(null=True, blank=True)
    authorization_code = models.CharField(max_length=20, blank=True)
    payment_type_code = models.CharField(max_length=10, blank=True)
    card_last4 = models.CharField(max_length=4, blank=True)
    respuesta = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-creado_en',)
        verbose_name = 'pago Webpay'
        verbose_name_plural = 'pagos Webpay'

    def __str__(self):
        return f'{self.buy_order} · {self.get_estado_display()}'


# ==========================================================
# HISTÓRICO DEL CONTRATO
# Copia nombre, tarifas, garantía, período y subtotal para que
# cambios posteriores en Maquinaria no alteren lo contratado.
# ==========================================================
class ItemContrato(models.Model):
    contrato = models.ForeignKey(Contrato, on_delete=models.CASCADE, related_name='items')
    maquinaria = models.ForeignKey(
        Maquinaria, on_delete=models.SET_NULL, null=True, blank=True, related_name='items_contrato'
    )
    unidades_asignadas = models.ManyToManyField(UnidadFlota, blank=True, related_name='items_contrato')
    maquinaria_nombre = models.CharField(max_length=140)
    cantidad = models.PositiveIntegerField()
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    tarifa_diaria = models.DecimalField(max_digits=12, decimal_places=0)
    tarifa_semanal = models.DecimalField(max_digits=12, decimal_places=0)
    garantia = models.DecimalField(max_digits=12, decimal_places=0)
    subtotal = models.DecimalField(max_digits=14, decimal_places=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(fecha_fin__gt=models.F('fecha_inicio')), name='item_contrato_fechas_validas')
        ]

    def __str__(self):
        return f'{self.cantidad} × {self.maquinaria_nombre}'


# ==========================================================
# ASIGNACIÓN AUTOMÁTICA DE ROL
# Usuarios normales nacen como Empresa; usuarios staff creados
# por consola reciben el rol Ejecutivo para el panel propio.
# ==========================================================
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def crear_perfil_usuario(sender, instance, created, **kwargs):
    if created:
        rol = PerfilUsuario.EJECUTIVO if instance.is_staff else PerfilUsuario.EMPRESA
        PerfilUsuario.objects.create(usuario=instance, rol=rol)


@receiver(post_save, sender=Maquinaria)
def sincronizar_unidades_flota(sender, instance, **kwargs):
    """Crea o retira IDs sin historial para mantener la cantidad declarada."""
    for numero in range(1, instance.cantidad + 1):
        UnidadFlota.objects.get_or_create(
            maquinaria=instance,
            codigo=f'MQ-{instance.pk:03d}-{numero:02d}',
        )
    sobrantes = instance.unidades.filter(items_contrato__isnull=True).order_by('-codigo')
    exceso = instance.unidades.count() - instance.cantidad
    if exceso > 0:
        UnidadFlota.objects.filter(pk__in=list(sobrantes.values_list('pk', flat=True)[:exceso])).delete()
