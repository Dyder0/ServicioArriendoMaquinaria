from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import MaquinariaFilter
from .models import CarroArriendo, Contrato, ItemCarro, Maquinaria, PerfilUsuario
from .permissions import EsEjecutivo, EsEmpresa, MaquinariaPublicaOEjecutivo, tiene_rol
from .serializer import (
    CarroSerializer, ContratoSerializer, EstadoContratoSerializer, ItemCarroSerializer, MaquinariaSerializer,
)
from .services import cambiar_estado_contrato, crear_contrato


# ==========================================================
# CRUD DE MAQUINARIA
# Lectura pública de activos y escritura protegida por rol. DRF
# aporta POST y las rutas de detalle GET/PUT/PATCH/DELETE.
# ==========================================================
class MaquinariaViewSet(viewsets.ModelViewSet):
    serializer_class = MaquinariaSerializer
    permission_classes = (MaquinariaPublicaOEjecutivo,)
    filter_backends = (DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter)
    filterset_class = MaquinariaFilter
    search_fields = ('nombre', 'categoria', 'descripcion')
    ordering_fields = ('nombre', 'categoria', 'tarifa_diaria', 'tarifa_semanal', 'cantidad')

    def get_queryset(self):
        queryset = Maquinaria.objects.all()
        if not tiene_rol(self.request.user, PerfilUsuario.EJECUTIVO):
            queryset = queryset.filter(activo=True)
        return queryset


# ==========================================================
# API DEL CARRO PERSISTENTE
# GET recupera, POST agrega/reutiliza, PATCH guarda cantidad y
# fechas, y DELETE elimina solo ítems del usuario autenticado.
# Agregar un ítem no modifica reservas ni contratos.
# ==========================================================
class CarroArriendoAPIView(APIView):
    permission_classes = (EsEmpresa,)

    @extend_schema(responses=CarroSerializer)
    def get(self, request):
        carro, _ = CarroArriendo.objects.get_or_create(usuario=request.user)
        return Response(CarroSerializer(carro, context={'request': request}).data)

    @extend_schema(request=ItemCarroSerializer, responses=CarroSerializer)
    def post(self, request):
        carro, _ = CarroArriendo.objects.get_or_create(usuario=request.user)
        payload = request.data.copy()
        payload.pop('fecha_inicio', None)
        payload.pop('fecha_fin', None)
        serializer = ItemCarroSerializer(data=payload, context={'request': request})
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        existente = carro.items.filter(maquinaria=datos['maquinaria']).first()
        if existente:
            nueva_cantidad = existente.cantidad + datos['cantidad']
            if nueva_cantidad > existente.maquinaria.cantidad:
                return Response({'cantidad': ['Supera las unidades de la flota.']}, status=status.HTTP_400_BAD_REQUEST)
            existente.cantidad = nueva_cantidad
            existente.save(update_fields=('cantidad',))
        else:
            serializer.save(carro=carro)
        carro.refresh_from_db()
        return Response(CarroSerializer(carro, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ItemCarroSerializer, responses=CarroSerializer)
    def patch(self, request):
        item = get_object_or_404(ItemCarro, pk=request.data.get('item_id'), carro__usuario=request.user)
        payload = request.data.copy()
        payload.pop('item_id', None)
        payload.pop('maquinaria', None)
        serializer = ItemCarroSerializer(item, data=payload, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(CarroSerializer(item.carro, context={'request': request}).data)

    @extend_schema(parameters=[], responses=CarroSerializer)
    def delete(self, request):
        item_id = request.data.get('item_id') or request.query_params.get('item_id')
        item = get_object_or_404(ItemCarro, pk=item_id, carro__usuario=request.user)
        carro = item.carro
        item.delete()
        return Response(CarroSerializer(carro, context={'request': request}).data)


# ==========================================================
# API DE CHECKOUT E HISTORIAL
# Checkout delega la atomicidad al servicio; el historial queda
# limitado al usuario Empresa autenticado.
# ==========================================================
class CheckoutAPIView(APIView):
    permission_classes = (EsEmpresa,)

    @extend_schema(request=None, responses=ContratoSerializer)
    def post(self, request):
        try:
            contrato = crear_contrato(request.user)
        except (CarroArriendo.DoesNotExist, ValueError) as error:
            return Response({'detail': str(error) or 'No existe un carro.'}, status=status.HTTP_409_CONFLICT)
        return Response(ContratoSerializer(contrato).data, status=status.HTTP_201_CREATED)


class MisContratosAPIView(APIView):
    permission_classes = (EsEmpresa,)

    @extend_schema(responses=ContratoSerializer(many=True))
    def get(self, request):
        contratos = Contrato.objects.filter(usuario=request.user).prefetch_related('items')
        return Response(ContratoSerializer(contratos, many=True).data)


# ==========================================================
# CAMBIO DE ESTADO EXCLUSIVO DEL EJECUTIVO
# El serializer valida el CHOICE y el servicio aplica transición,
# bloqueo y disponibilidad antes de confirmar PAGADO.
# ==========================================================
class EstadoContratoAPIView(APIView):
    permission_classes = (EsEjecutivo,)

    @extend_schema(request=EstadoContratoSerializer, responses=ContratoSerializer)
    def patch(self, request, pk):
        serializer = EstadoContratoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            contrato = cambiar_estado_contrato(pk, serializer.validated_data['estado'])
        except Contrato.DoesNotExist:
            return Response({'detail': 'Contrato no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as error:
            return Response({'detail': str(error)}, status=status.HTTP_409_CONFLICT)
        return Response(ContratoSerializer(contrato).data)
