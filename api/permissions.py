"""Role-based permission classes (Django Groups 'admin' / 'manager').

is_superuser is always treated as admin. The global default is IsAuthenticated
(settings REST_FRAMEWORK) — these tighten specific endpoints (user management,
licensing mutations) to admin-only in later phases."""
from rest_framework.permissions import BasePermission


def _in_groups(user, names):
    return bool(user and user.is_authenticated and
                (user.is_superuser or user.groups.filter(name__in=names).exists()))


class IsAdmin(BasePermission):
    message = "Требуются права администратора."

    def has_permission(self, request, view):
        return _in_groups(request.user, ["admin"])


class IsManagerOrAdmin(BasePermission):
    message = "Требуются права менеджера или администратора."

    def has_permission(self, request, view):
        return _in_groups(request.user, ["admin", "manager"])
