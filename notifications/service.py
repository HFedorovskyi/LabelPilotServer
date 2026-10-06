"""Raise and resolve notifications. Callers describe the cause with a stable `key`
(e.g. "station:<uuid>:offline"); a repeat of an open cause bumps its count and time
instead of adding a row, and a cause that comes back after being resolved reopens it,
so every user sees it as unread again. Never raises: a notification must not break the
request or the report that produced it."""
import hashlib
import logging

from django.db import transaction
from django.utils import timezone

from .models import Notification

log = logging.getLogger(__name__)

SEVERITY_RANK = {'critical': 0, 'error': 1, 'warning': 2, 'info': 3}
RETENTION_DAYS = 30


def raise_notification(key, code, severity, params=None, link_tab='', link_id='', now=None):
    now = now or timezone.now()
    params = params or {}
    try:
        with transaction.atomic():
            row = (Notification.objects.select_for_update()
                   .filter(key=key).order_by('-last_at').first())
            if row is None:
                return Notification.objects.create(
                    key=key, code=code, severity=severity, params=params,
                    link_tab=link_tab, link_id=str(link_id or ''), first_at=now, last_at=now,
                )
            row.code, row.severity, row.params = code, severity, params
            row.link_tab, row.link_id = link_tab, str(link_id or '')
            row.last_at = now
            if row.resolved_at is not None:
                row.resolved_at = None
                row.first_at = now
                row.count = 1
            else:
                row.count += 1
            row.save()
            return row
    except Exception:  # pragma: no cover - defensive, logged
        log.exception("could not raise notification %s", key)
        return None


def ensure_notification(key, code, severity, params=None, link_tab='', link_id='', now=None):
    """Like raise_notification, but a cause that is still open only refreshes its
    params (no repeat count, no "unread again") — for states a periodic check sees
    again and again (station offline, licence expiring)."""
    try:
        row = Notification.objects.filter(key=key, resolved_at__isnull=True).first()
        if row is not None:
            changed = row.params != (params or {}) or row.severity != severity or row.code != code
            if changed:
                Notification.objects.filter(pk=row.pk).update(code=code, severity=severity, params=params or {})
            return row
    except Exception:  # pragma: no cover
        log.exception("could not read notification %s", key)
        return None
    return raise_notification(key, code, severity, params, link_tab, link_id, now)


def resolve(key, now=None):
    try:
        return Notification.objects.filter(key=key, resolved_at__isnull=True).update(resolved_at=now or timezone.now())
    except Exception:  # pragma: no cover
        log.exception("could not resolve notification %s", key)
        return 0


def resolve_prefix(prefix, keep=(), now=None):
    """Resolve every open notification whose key starts with `prefix`, except `keep`."""
    try:
        return (Notification.objects.filter(key__startswith=prefix, resolved_at__isnull=True)
                .exclude(key__in=list(keep)).update(resolved_at=now or timezone.now()))
    except Exception:  # pragma: no cover
        log.exception("could not resolve notifications %s*", prefix)
        return 0


def message_key(text):
    """Short stable hash of a free-text message, so the same station error repeats into
    one notification while different errors stay separate."""
    normalized = ' '.join(str(text or '').lower().split())[:500]
    return hashlib.sha1(normalized.encode('utf-8')).hexdigest()[:12]


def purge_old(now=None):
    """Drop resolved problems and informational events older than the retention."""
    from django.db.models import Q

    now = now or timezone.now()
    cutoff = now - timezone.timedelta(days=RETENTION_DAYS)
    return Notification.objects.filter(
        Q(resolved_at__lt=cutoff) | Q(severity='info', last_at__lt=cutoff)
    ).delete()[0]
