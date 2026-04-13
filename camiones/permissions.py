from rest_framework.permissions import BasePermission


class EsOperadorStock(BasePermission):
    """
    El usuario debe pertenecer al grupo 'operador_stock' o ser staff.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        return request.user.groups.filter(name='operador_stock').exists()
