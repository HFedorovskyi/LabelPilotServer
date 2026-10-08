"""Admin-only user management (Django auth Users + 'admin'/'manager' Group roles).

Powers the web UI page «Доступ к серверу». Guards against locking the install out of admin
access: you cannot delete/deactivate/demote yourself or the last remaining admin."""
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User, Group
from rest_framework import viewsets, serializers, status
from rest_framework.response import Response

from api.permissions import IsAdmin
from api.auth_views import role_of, ensure_groups
from api.login_throttle import clear_login
from api.passwords import password_problem
from api.i18n import tr


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    # «Кто это»: a name or job title, so a login like "smena2" means something.
    name = serializers.CharField(source="first_name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "name", "is_active", "is_superuser", "role", "last_login", "date_joined"]

    def get_role(self, obj):
        return role_of(obj)


def _name(request):
    return (request.data.get("name") or "").strip()[:150]


def _active_admin_count(exclude_id=None):
    qs = User.objects.filter(is_active=True)
    if exclude_id is not None:
        qs = qs.exclude(id=exclude_id)
    return sum(1 for u in qs if role_of(u) == "admin")


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("username")
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]

    @staticmethod
    def _apply_role(user, role):
        if role not in ("admin", "manager"):
            return
        ensure_groups()
        user.groups.set([Group.objects.get(name=role)])  # role is exclusive

    def create(self, request, *args, **kwargs):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        role = request.data.get("role") or "manager"
        if not username or not password:
            return Response({"detail": tr('common.loginPasswordRequired')}, status=status.HTTP_400_BAD_REQUEST)
        if role not in ("admin", "manager"):
            return Response({"detail": tr('user.invalidRole')}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(username=username).exists():
            return Response({"detail": tr('user.alreadyExists')}, status=status.HTTP_400_BAD_REQUEST)
        problem = password_problem(password, User(username=username, first_name=_name(request)))
        if problem:
            return Response({"detail": problem}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.create_user(username=username, password=password, is_staff=True, first_name=_name(request))
        self._apply_role(user, role)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        user = self.get_object()
        new_role = request.data.get("role")
        new_active = request.data.get("is_active")
        new_password = request.data.get("password")
        if "name" in request.data:
            user.first_name = _name(request)
        if new_password:
            problem = password_problem(new_password, user)
            if problem:
                return Response({"detail": problem}, status=status.HTTP_400_BAD_REQUEST)

        # Guard: never strip the LAST admin (demote or deactivate) or self-demote/deactivate.
        demoting = new_role == "manager" and role_of(user) == "admin"
        deactivating = new_active is False and user.is_active
        if (demoting or deactivating) and role_of(user) == "admin" and _active_admin_count(exclude_id=user.id) == 0:
            return Response({"detail": tr('user.cannotDemoteLastAdmin')},
                            status=status.HTTP_400_BAD_REQUEST)
        if deactivating and user.id == request.user.id:
            return Response({"detail": tr('user.cannotDeactivateSelf')}, status=status.HTTP_400_BAD_REQUEST)

        if new_role is not None:
            self._apply_role(user, new_role)
        if new_active is not None:
            user.is_active = bool(new_active)
        if new_password:
            # Ends that user's other sessions (Django checks the password hash per session);
            # an admin changing their own password stays signed in here.
            user.set_password(new_password)
        user.save()
        if new_password:
            clear_login(user.username)
            if user.id == request.user.id:
                update_session_auth_hash(request, user)
        return Response(UserSerializer(user).data)

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user.id == request.user.id:
            return Response({"detail": tr('user.cannotDeleteSelf')}, status=status.HTTP_400_BAD_REQUEST)
        if role_of(user) == "admin" and _active_admin_count(exclude_id=user.id) == 0:
            return Response({"detail": tr('user.cannotDeleteLastAdmin')},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)
