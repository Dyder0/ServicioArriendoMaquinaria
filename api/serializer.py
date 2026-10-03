from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.utils import timezone

from .models import CarroArriendo, Contrato, ItemCarro, ItemContrato, Maquinaria, UnidadFlota


# ==========================================================
# JWT CON CLAIM PERSONALIZADO
# SimpleJWT genera access y refresh; get_token incorpora "rol"
# dentro del token firmado y validate lo expone en la respuesta.
# ==========================================================
def rol_usuario(usuario):
    try:
        return usuario.perfil.rol
    except Exception:
        return None


class TokenConRolSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['rol'] = rol_usuario(user)
        return token

    def validate(self, attrs):
        datos = super().validate(attrs)
        datos['rol'] = rol_usuario(self.user)
        return datos


# ==========================================================
# CATÁLOGO Y DISPONIBILIDAD CONSULTABLE
# Si la petición incluye fecha_inicio/fecha_fin, el catálogo
# informa unidades libres para ese rango sin reservarlas.
# ==========================================================
class UnidadFlotaSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnidadFlota
        fields = ('id', 'codigo', 'estado', 'permiso_circulacion')


class MaquinariaSerializer(serializers.ModelSerializer):
    disponibilidad = serializers.SerializerMethodField()
    unidades = UnidadFlotaSerializer(many=True, read_only=True)

    class Meta:
        model = Maquinaria
        fields = '__all__'
        read_only_fields = ('creado_en', 'actualizado_en')

    def get_disponibilidad(self, maquinaria) -> int:
        request = self.context.get('request')
        if not request:
            return maquinaria.cantidad
        inicio, fin = request.query_params.get('fecha_inicio'), request.query_params.get('fecha_fin')
        if not inicio or not fin:
            return maquinaria.cantidad
        try:
            inicio = serializers.DateField().to_internal_value(inicio)
            fin = serializers.DateField().to_internal_value(fin)
            if fin <= inicio:
                return maquinaria.cantidad
            return maquinaria.disponibilidad(inicio, fin)
        except serializers.ValidationError:
            return maquinaria.cantidad

    def validate_cantidad(self, cantidad):
        if self.instance:
            asignadas = self.instance.unidades.filter(items_contrato__isnull=False).distinct().count()
            if cantidad < asignadas:
                raise serializers.ValidationError(f'No puede ser menor que las {asignadas} unidades con historial.')
        return cantidad


# ==========================================================
# VALIDACIÓN DEL ÍTEM DE CARRO
# Admite fechas vacías mientras se arma el carro, pero rechaza
# pares incompletos, rangos invertidos y cantidades sin flota.
# ==========================================================
class ItemCarroSerializer(serializers.ModelSerializer):
    maquinaria_detalle = MaquinariaSerializer(source='maquinaria', read_only=True)
    dias = serializers.IntegerField(read_only=True)
    subtotal_arriendo = serializers.DecimalField(max_digits=14, decimal_places=0, read_only=True)
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=0, read_only=True)
    semanas = serializers.IntegerField(read_only=True)
    dias_restantes = serializers.IntegerField(read_only=True)
    fechas_validas = serializers.BooleanField(read_only=True)

    class Meta:
        model = ItemCarro
        fields = ('id', 'maquinaria', 'maquinaria_detalle', 'cantidad', 'fecha_inicio', 'fecha_fin', 'dias',
                  'semanas', 'dias_restantes', 'fechas_validas', 'subtotal_arriendo', 'subtotal')
        extra_kwargs = {
            'fecha_inicio': {'required': False, 'allow_null': True},
            'fecha_fin': {'required': False, 'allow_null': True},
        }

    def validate(self, datos):
        inicio = datos.get('fecha_inicio', getattr(self.instance, 'fecha_inicio', None))
        fin = datos.get('fecha_fin', getattr(self.instance, 'fecha_fin', None))
        if inicio and fin and fin <= inicio:
            raise serializers.ValidationError({'fecha_fin': 'Debe ser posterior a fecha_inicio.'})
        if inicio and inicio <= timezone.localdate():
            raise serializers.ValidationError({'fecha_inicio': 'El arriendo debe comenzar desde mañana.'})
        if bool(inicio) != bool(fin):
            raise serializers.ValidationError('Debes indicar ambas fechas o dejar ambas vacías.')
        maquinaria = datos.get('maquinaria', getattr(self.instance, 'maquinaria', None))
        if maquinaria and not maquinaria.activo:
            raise serializers.ValidationError({'maquinaria': 'Esta maquinaria no está activa.'})
        if maquinaria and datos.get('cantidad', 1) > maquinaria.cantidad:
            raise serializers.ValidationError({'cantidad': 'Supera las unidades de la flota.'})
        return datos


class CarroSerializer(serializers.ModelSerializer):
    items = ItemCarroSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=14, decimal_places=0, read_only=True)

    class Meta:
        model = CarroArriendo
        fields = ('id', 'actualizado_en', 'items', 'total')


class ItemContratoSerializer(serializers.ModelSerializer):
    unidades_asignadas = UnidadFlotaSerializer(many=True, read_only=True)

    class Meta:
        model = ItemContrato
        fields = '__all__'


# ==========================================================
# CONTRATO DE SOLO LECTURA
# Expone al cliente el encabezado histórico y todos sus ítems;
# el alta se realiza exclusivamente mediante checkout.
# ==========================================================
class ContratoSerializer(serializers.ModelSerializer):
    items = ItemContratoSerializer(many=True, read_only=True)
    empresa = serializers.CharField(source='usuario.username', read_only=True)

    class Meta:
        model = Contrato
        fields = ('id', 'empresa', 'estado', 'total', 'creado_en', 'actualizado_en', 'items')
        read_only_fields = fields


class EstadoContratoSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=Contrato.ESTADOS)
