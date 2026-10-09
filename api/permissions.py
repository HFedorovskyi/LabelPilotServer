"""Role-based permission classes (Django Groups 'admin' / 'manager').

is_superuser is always treated as admin. The global default is IsAuthenticated
(settings REST_FRAMEWORK) — these tighten specific endpoints (user management,
licensing mutations) to admin-only in later phases."""
from rest_framework.permissions import BasePermission

from .i18n import tr


def _in_groups(user, names):
    return bool(user and user.is_authenticated and
                (user.is_superuser or user.groups.filter(name__in=names).exists()))


class IsAdmin(BasePermission):
    # `message` is read by DRF only when permission is denied; a property resolves it in
    # the request's language (set by LangMiddleware) instead of binding ru at import time.
    @property
    def message(self):
        return tr("perm.adminRequired")

    def has_permission(self, request, view):
        return _in_groups(request.user, ["admin"])


class IsManagerOrAdmin(BasePermission):
    @property
    def message(self):
        return tr("perm.managerOrAdminRequired")

    def has_permission(self, request, view):
        return _in_groups(request.user, ["admin", "manager"])
