from django.contrib.auth import views as auth_views
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import auth_views as registro_views
from . import client_views, views
from .serializer import TokenConRolSerializer
from rest_framework_simplejwt.views import TokenObtainPairView


class TokenConRolView(TokenObtainPairView):
    serializer_class = TokenConRolSerializer


router = DefaultRouter()
router.register('maquinarias', views.MaquinariaViewSet, basename='maquinaria')

urlpatterns = [
    path('', client_views.index_view, name='home'),
    path('registro/', registro_views.register_view, name='register'),
    path('ingresar/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('salir/', auth_views.LogoutView.as_view(), name='logout'),
    path('carro/', client_views.carro_view, name='carro_web'),
    path('carro/agregar/<int:pk>/', client_views.agregar_carro, name='agregar_carro_web'),
    path('carro/actualizar/<int:pk>/', client_views.actualizar_item_carro, name='actualizar_item_carro_web'),
    path('carro/eliminar/<int:pk>/', client_views.eliminar_item_carro, name='eliminar_item_carro_web'),
    path('contratos/checkout/', client_views.checkout_web, name='checkout_web'),
    path('mis-contratos/', client_views.mis_contratos_view, name='mis_contratos_web'),
    path('panel/', client_views.panel_view, name='panel'),
    path('panel/maquinarias/nueva/', client_views.maquinaria_form_view, name='maquinaria_crear_web'),
    path('panel/maquinarias/<int:pk>/editar/', client_views.maquinaria_form_view, name='maquinaria_editar_web'),
    path('panel/maquinarias/<int:pk>/eliminar/', client_views.maquinaria_eliminar_view, name='maquinaria_eliminar_web'),
    path('panel/contratos/<int:pk>/estado/', client_views.contrato_estado_view, name='contrato_estado_web'),

    path('api/', include(router.urls)),
    path('api/carro-arriendo/', views.CarroArriendoAPIView.as_view(), name='api_carro'),
    path('api/contratos/checkout/', views.CheckoutAPIView.as_view(), name='api_checkout'),
    path('api/mis-contratos/', views.MisContratosAPIView.as_view(), name='api_mis_contratos'),
    path('api/contratos/<int:pk>/estado/', views.EstadoContratoAPIView.as_view(), name='api_contrato_estado'),
    path('api/token/', TokenConRolView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
