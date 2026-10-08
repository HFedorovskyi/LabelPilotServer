"""Brute-force guard for the sign-in. Counts wrong passwords per computer (IP) and login:
5 in a row closes that login on that computer for 15 minutes, 20 over all logins closes the
computer. Locking per computer, not per login, keeps a stranger on the plant network from
locking the real admin out. Each lock raises a notification for the admins."""
import math
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from server_activity.models import LoginThrottle

PER_LOGIN = 5
PER_COMPUTER = 20
WINDOW = timedelta(minutes=15)
LOCK = timedelta(minutes=15)


def client_ip(request):
    return (request.META.get("REMOTE_ADDR") or "unknown")[:64]


def _key(username):
    return (username or "").strip().lower()[:150]


def locked_seconds(ip, username, now=None):
    """Seconds until this computer may try this login again, 0 when it may now."""
    now = now or timezone.now()
    until = (LoginThrottle.objects
             .filter(ip=ip, username__in=[_key(username), ""], locked_until__gt=now)
             .order_by("-locked_until").values_list("locked_until", flat=True).first())
    return max(1, math.ceil((until - now).total_seconds())) if until else 0


def _bump(ip, username, limit, now):
    row, _ = LoginThrottle.objects.select_for_update().get_or_create(
        ip=ip, username=username, defaults={"last_failure_at": now})
    if row.last_failure_at < now - WINDOW:
        row.failures = 0
    row.failures += 1
    row.last_failure_at = now
    locked = row.failures >= limit
    if locked:
        row.failures = 0
        row.locked_until = now + LOCK
    row.save()
    return limit - row.failures if not locked else 0, locked


def record_failure(ip, username, now=None):
    """Count a wrong password. Returns (attempts left for this login, seconds locked)."""
    now = now or timezone.now()
    login = _key(username)
    with transaction.atomic():
        LoginThrottle.objects.filter(last_failure_at__lt=now - timedelta(days=1), locked_until__isnull=True).delete()
        left, login_locked = _bump(ip, login, PER_LOGIN, now) if login else (PER_LOGIN, False)
        _, computer_locked = _bump(ip, "", PER_COMPUTER, now)
    if login_locked or computer_locked:
        from notifications.service import raise_notification
        if computer_locked:
            raise_notification(f"auth:locked:{ip}", "auth.locked_computer", "warning",
                               {"ip": ip, "count": PER_COMPUTER, "minutes": int(LOCK.total_seconds() // 60)}, link_tab="users")
        else:
            raise_notification(f"auth:locked:{ip}:{login}", "auth.locked", "warning",
                               {"ip": ip, "login": username.strip()[:150], "count": PER_LOGIN,
                                "minutes": int(LOCK.total_seconds() // 60)}, link_tab="users")
        return 0, locked_seconds(ip, username, now)
    return left, 0


def record_success(ip, username):
    LoginThrottle.objects.filter(ip=ip, username=_key(username)).delete()


def clear_login(username):
    """A new password was set: lift that login's locks on every computer."""
    LoginThrottle.objects.filter(username=_key(username)).delete()
