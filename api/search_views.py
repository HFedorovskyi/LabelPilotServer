"""Header command-palette search + the notifications (bell) alert feed.

Both are read-only and lightweight. Search spans the catalog, stations, templates and jobs and
returns a flat, capped result list each tagged with the SPA tab to navigate to. Notifications
surfaces recent station errors/warnings + server events; unread state is tracked client-side."""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db.models import Q
from django.utils import timezone

from Nomenclature.models import Nomenclature
from label_stations.models import LabelsStations
from LabelTemplates.models import LabelTemplates
from BarcodeTemplates.models import BarcodeTemplate
from print_jobs.models import PrintJob
from ProductionLogs.models import StationLog
from server_activity.models import ServerEvent


class SearchView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        q = (request.query_params.get('q') or '').strip()
        results = []
        if len(q) < 2:
            return Response({'query': q, 'results': results})

        PER = 6

        for n in Nomenclature.objects.filter(
            Q(name__icontains=q) | Q(article__icontains=q)
        ).order_by('name')[:PER]:
            results.append({'type': 'product', 'tab': 'catalog', 'id': n.pk,
                            'title': n.name, 'subtitle': n.article})

        # station_number is an integer column — only match it when q is numeric.
        sq = Q(station_name__icontains=q) | Q(station_ip__icontains=q)
        if q.isdigit():
            sq = sq | Q(station_number=int(q))
        for s in LabelsStations.objects.filter(sq).order_by('station_number')[:PER]:
            results.append({'type': 'station', 'tab': 'stations', 'id': s.pk,
                            'title': s.station_name or f'Станция {s.station_number}',
                            'subtitle': s.station_ip or ''})

        for lt in LabelTemplates.objects.filter(name__icontains=q).order_by('name')[:PER]:
            results.append({'type': 'label', 'tab': 'labels', 'id': lt.pk, 'title': lt.name, 'subtitle': ''})

        for bt in BarcodeTemplate.objects.filter(name__icontains=q).order_by('name')[:PER]:
            results.append({'type': 'barcode', 'tab': 'barcodes', 'id': bt.pk, 'title': bt.name, 'subtitle': ''})

        for j in PrintJob.objects.select_related('nomenclature').filter(
            Q(nomenclature__name__icontains=q) | Q(batch_number__icontains=q)
        ).order_by('-created_at')[:PER]:
            results.append({'type': 'job', 'tab': 'print_tasks', 'id': j.pk,
                            'title': (j.nomenclature.name if j.nomenclature else f'#{j.pk}'),
                            'subtitle': j.batch_number or ''})

        return Response({'query': q, 'results': results})


class NotificationsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        items = []

        for log in StationLog.objects.select_related('station').filter(
            level__in=['ERROR', 'WARNING']
        ).order_by('-timestamp')[:20]:
            items.append({
                'id': f'log-{log.id}',
                'kind': 'station',
                'level': log.level,
                'title': log.message,
                'subtitle': (log.station.station_name if log.station else ''),
                'created_at': log.timestamp.isoformat() if log.timestamp else None,
            })

        for ev in ServerEvent.objects.order_by('-created_at')[:20]:
            items.append({
                'id': f'ev-{ev.id}',
                'kind': 'server',
                'level': 'INFO',
                'title': ev.get_action_display() or ev.description,
                'subtitle': ev.description if ev.get_action_display() else '',
                'created_at': ev.created_at.isoformat(),
            })

        items.sort(key=lambda x: x['created_at'] or '', reverse=True)
        return Response({'notifications': items[:25], 'generated_at': timezone.now().isoformat()})
