"""Session-cookie auth for the web UI + a self-disabling first-run bootstrap.

Same-origin SPA + API + admin on one Waitress process, so a Django sessionid cookie
is sent automatically to /api/v1 (no CORS, no token storage). Roles = Django Groups
'admin'/'manager'. Bootstrap creates the FIRST admin only while the user table is empty,
then refuses forever (409) — so it can never add a backdoor admin later."""
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User, Group
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated

from api.i18n import tr
from api.login_throttle import client_ip, locked_seconds, record_failure, record_success
from api.passwords import password_problem

_MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"


def ensure_groups():
    for name in ("admin", "manager"):
        Group.objects.get_or_create(name=name)


def role_of(user):
    if not (user and user.is_authenticated):
        return None
    if user.is_superuser or user.groups.filter(name="admin").exists():
        return "admin"
    if user.groups.filter(name="manager").exists():
        return "manager"
    return "user"


def user_payload(user):
    return {
        "id": user.id,
        "username": user.username,
        "role": role_of(user),
        "is_superuser": user.is_superuser,
    }


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """GET to plant the csrftoken cookie so the SPA can send X-CSRFToken on writes."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"detail": "csrf cookie set"})


def _locked(seconds):
    return Response({"detail": tr('auth.locked', minutes=max(1, -(-seconds // 60))), "locked_for": seconds},
                    status=status.HTTP_429_TOO_MANY_REQUESTS)


class LoginView(APIView):
    """Wrong passwords are counted per computer and login (api/login_throttle.py); while a
    lock lasts the password is not even checked. `attempts_left` lets the page warn early."""
    permission_classes = [AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        ip = client_ip(request)
        wait = locked_seconds(ip, username)
        if wait:
            return _locked(wait)
        user = authenticate(request, username=username, password=password)
        if user is None or not user.is_active:
            left, wait = record_failure(ip, username)
            if wait:
                return _locked(wait)
            return Response({"detail": tr('auth.invalidCredentials'), "attempts_left": left},
                            status=status.HTTP_401_UNAUTHORIZED)
        record_success(ip, username)
        login(request, user)
        return Response(user_payload(user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({"detail": "ok"})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(user_payload(request.user))


class BootstrapStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"needs_bootstrap": not User.objects.exists()})


class BootstrapView(APIView):
    """Create the first admin when there are NO users. Self-disabling: 409 once any exists."""
    permission_classes = [AllowAny]

    def post(self, request):
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""
        if not username or not password:
            return Response({"detail": tr('common.loginPasswordRequired')},
                            status=status.HTTP_400_BAD_REQUEST)
        problem = password_problem(password, User(username=username))
        if problem:
            return Response({"detail": problem}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            if User.objects.exists():
                return Response({"detail": tr('auth.adminExists')},
                                status=status.HTTP_409_CONFLICT)
            ensure_groups()
            user = User.objects.create_superuser(username=username, password=password)
            user.groups.add(Group.objects.get(name="admin"))
        login(request, user, backend=_MODEL_BACKEND)
        return Response(user_payload(user), status=status.HTTP_201_CREATED)
