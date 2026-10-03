import django_filters

from .models import Maquinaria


# ==========================================================
# FILTROS DEL CATÁLOGO
# django-filter traduce estos parámetros a consultas ORM reales;
# búsqueda textual y ordering se complementan en MaquinariaViewSet.
# ==========================================================
class MaquinariaFilter(django_filters.FilterSet):
    precio_min = django_filters.NumberFilter(field_name='tarifa_diaria', lookup_expr='gte')
    precio_max = django_filters.NumberFilter(field_name='tarifa_diaria', lookup_expr='lte')
    semanal_min = django_filters.NumberFilter(field_name='tarifa_semanal', lookup_expr='gte')
    semanal_max = django_filters.NumberFilter(field_name='tarifa_semanal', lookup_expr='lte')

    class Meta:
        model = Maquinaria
        fields = ('categoria', 'activo')
