from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification, NotificationSeen
from .service import SEVERITY_RANK

LIST_LIMIT = 60
BADGE_SEVERITIES = ('critical', 'error', 'warning')
TOAST_SEVERITIES = ('critical', 'error')


def _serialize(n, seen_at):
    return {
        'id': n.pk,
        'code': n.code,
        'severity': n.severity,
        'params': n.params,
        'link_tab': n.link_tab,
        'link_id': n.link_id,
        'count': n.count,
        'first_at': n.first_at.isoformat(),
        'last_at': n.last_at.isoformat(),
        'resolved_at': n.resolved_at.isoformat() if n.resolved_at else None,
        'unread': seen_at is None or n.last_at > seen_at,
    }


def _seen_at(user):
    row = NotificationSeen.objects.filter(user=user).first()
    return row.seen_at if row else None


class NotificationsView(APIView):
    """GET /api/v1/notifications/?since=<iso> — open problems first, then recent events.
    `unread` counts open critical/error/warning items the user has not seen; `toasts`
    lists open critical/error items raised or repeated after `since` (the client's
    previous poll), so the UI can pop them up once."""

    def get(self, request):
        seen_at = _seen_at(request.user)
        now = timezone.now()
        open_items = list(Notification.objects.filter(resolved_at__isnull=True).order_by('-last_at')[:LIST_LIMIT])
        open_items.sort(key=lambda n: (SEVERITY_RANK.get(n.severity, 9), -n.last_at.timestamp()))
        recent = list(Notification.objects.filter(resolved_at__isnull=False).order_by('-last_at')[:20])

        unread_q = Q(resolved_at__isnull=True, severity__in=BADGE_SEVERITIES)
        if seen_at is not None:
            unread_q &= Q(last_at__gt=seen_at)
        unread = {s: 0 for s in BADGE_SEVERITIES}
        for severity in Notification.objects.filter(unread_q).values_list('severity', flat=True):
            unread[severity] += 1

        since = parse_datetime(request.query_params.get('since') or '')
        toasts = []
        if since is not None:
            toasts = [
                _serialize(n, seen_at)
                for n in Notification.objects.filter(
                    resolved_at__isnull=True, severity__in=TOAST_SEVERITIES, last_at__gt=since,
                ).order_by('last_at')[:5]
            ]

        return Response({
            'items': [_serialize(n, seen_at) for n in open_items + recent],
            'unread': {**unread, 'total': sum(unread.values())},
            'toasts': toasts,
            'seen_at': seen_at.isoformat() if seen_at else None,
            'server_time': now.isoformat(),
        })


class NotificationsSeenView(APIView):
    """POST /api/v1/notifications/seen/ — the user opened the list: all read up to now."""

    def post(self, request):
        now = timezone.now()
        NotificationSeen.objects.update_or_create(user=request.user, defaults={'seen_at': now})
        return Response({'seen_at': now.isoformat()})
