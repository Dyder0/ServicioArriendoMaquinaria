from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import PerfilUsuario


# ==========================================================
# PERMISOS DRF POR ROL
# Centraliza la lectura del perfil para evitar confiar en datos
# enviados por el cliente o en claims sin usuario autenticado.
# ==========================================================
def tiene_rol(usuario, rol):
    return bool(usuario and usuario.is_authenticated and hasattr(usuario, 'perfil') and usuario.perfil.rol == rol)


class EsEmpresa(BasePermission):
    def has_permission(self, request, view):
        return tiene_rol(request.user, PerfilUsuario.EMPRESA)


class EsEjecutivo(BasePermission):
    def has_permission(self, request, view):
        return tiene_rol(request.user, PerfilUsuario.EJECUTIVO)


# ==========================================================
# CATÁLOGO PÚBLICO / ESCRITURA EJECUTIVA
# Los métodos seguros son públicos; crear, editar y eliminar
# maquinaria requiere EJECUTIVO_ARRIENDOS.
# ==========================================================
class MaquinariaPublicaOEjecutivo(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or tiene_rol(request.user, PerfilUsuario.EJECUTIVO)
