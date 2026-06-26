from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
from django.db.models import Count, Sum, F, FloatField, Q, Case, When, Min, Max
from django.db.models.functions import Coalesce, TruncHour, TruncDate, NullIf
from ProductionLogs.models import PrintedLabel, StationLog
from label_stations.models import LabelsStations
from print_jobs.models import PrintJob
from LabelTemplates.models import LabelTemplates
from BarcodeTemplates.models import BarcodeTemplate
from Nomenclature.models import Nomenclature
from server_activity.models import ServerEvent
import datetime
from api.i18n import tr


class StatisticsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Good production = non-deleted weighings. Deleted "отвесы" are surfaced separately below.
        good = PrintedLabel.objects.filter(is_deleted=False)

        total_labels = good.count()
        labels_today = good.filter(printed_at__gte=today).count()

        # Weight rule: a FIXED-weight product contributes its nominal Nomenclature.fixed_weight_grams;
        # a VARIABLE-weight product contributes the station-reported actual net weight. A fixed product
        # mis-configured with 0/NULL nominal falls back to the actual weighed value (NullIf) so a real
        # weighing is never silently counted as 0. Legacy rows with no weight count as 0 (outer Coalesce).
        weight_expr = Coalesce(
            Case(
                When(product__is_fixed_weight=True,
                     then=Coalesce(NullIf(F('product__fixed_weight_grams'), 0.0), F('weight_netto_grams'))),
                default=F('weight_netto_grams'),
                output_field=FloatField(),
            ),
            0.0,
            output_field=FloatField(),
        )
        total_weight_kg = round(good.aggregate(w=Coalesce(Sum(weight_expr), 0.0))['w'] / 1000.0, 2)
        weight_today_kg = round(
            good.filter(printed_at__gte=today).aggregate(w=Coalesce(Sum(weight_expr), 0.0))['w'] / 1000.0, 2
        )

        # ── Deleted weighings ("удалённые отвесы") — count + weight, today & total ──────
        # Bucket "today" by the DELETION time (deleted_at), not production time, so a pack printed
        # yesterday but deleted today counts today. Rare rows with no deleted_at fall back to printed_at.
        # Weight uses the SAME rule as good production (weight_expr) so the two totals are comparable.
        deleted_qs = PrintedLabel.objects.filter(is_deleted=True)
        deleted_today_qs = deleted_qs.annotate(_dt=Coalesce('deleted_at', 'printed_at')).filter(_dt__gte=today)
        deleted_total = deleted_qs.count()
        deleted_today = deleted_today_qs.count()
        deleted_weight_total_kg = round(deleted_qs.aggregate(w=Coalesce(Sum(weight_expr), 0.0))['w'] / 1000.0, 2)
        deleted_weight_today_kg = round(deleted_today_qs.aggregate(w=Coalesce(Sum(weight_expr), 0.0))['w'] / 1000.0, 2)

        # ── Throughput over time + yesterday delta (dashboard charts) ────────
        now = timezone.now()
        yesterday = today - datetime.timedelta(days=1)
        labels_yesterday = good.filter(
            printed_at__gte=yesterday, printed_at__lt=today
        ).count()

        start_24h = (now - datetime.timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
        hourly_map = {
            row['bucket']: row['c']
            for row in good.filter(printed_at__gte=start_24h)
            .annotate(bucket=TruncHour('printed_at')).values('bucket').annotate(c=Count('id'))
        }
        throughput_24h = [
            {
                "t": (start_24h + datetime.timedelta(hours=i)).isoformat(),
                "count": hourly_map.get(start_24h + datetime.timedelta(hours=i), 0),
            }
            for i in range(24)
        ]

        start_7d = (now - datetime.timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_map = {
            row['bucket']: row['c']
            for row in good.filter(printed_at__gte=start_7d)
            .annotate(bucket=TruncDate('printed_at')).values('bucket').annotate(c=Count('id'))
        }
        throughput_7d = [
            {
                "t": (start_7d + datetime.timedelta(days=i)).date().isoformat(),
                "count": daily_map.get((start_7d + datetime.timedelta(days=i)).date(), 0),
            }
            for i in range(7)
        ]

        # Top stations
        top_stations_qs = good.values(
            'station__station_name', 'station__station_number'
        ).annotate(count=Count('id')).order_by('-count')[:5]
        top_stations = [
            {
                "name": item['station__station_name'] or tr('stats.unknownStation'),
                "number": item['station__station_number'],
                "count": item['count']
            }
            for item in top_stations_qs
        ]

        # Top products
        top_products_qs = good.values(
            'product_name_snapshot'
        ).annotate(count=Count('id')).order_by('-count')[:5]
        top_products = [
            {
                "name": item['product_name_snapshot'] or tr('stats.unknownProduct'),
                "count": item['count']
            }
            for item in top_products_qs
        ]

        # Recent logs
        recent_logs_qs = StationLog.objects.select_related('station').order_by('-timestamp')[:10]
        recent_logs = [
            {
                "id": log.id,
                "station": log.station.station_name if log.station else tr('stats.unknownStation'),
                "level": log.level,
                "message": log.message,
                "timestamp": log.timestamp.isoformat()
            }
            for log in recent_logs_qs
        ]

        active_stations = LabelsStations.objects.filter(is_online=True).count()
        total_stations = LabelsStations.objects.count()

        # ── NEW: Readiness Check ─────────────────────────────────────────────
        products_count = Nomenclature.objects.count()
        templates_count = LabelTemplates.objects.count()
        barcode_templates_count = BarcodeTemplate.objects.count()
        pending_jobs_count = PrintJob.objects.filter(status='pending').count()

        # Products without any label template
        products_without_template = Nomenclature.objects.filter(
            templates_pack_label__isnull=True,
            templates_box_label__isnull=True
        ).count()

        # Stations that haven't synced in > 7 days (only offline/hybrid)
        stale_threshold = timezone.now() - datetime.timedelta(days=7)
        stations_stale_sync = LabelsStations.objects.filter(
            mode__in=['offline', 'hybrid']
        ).filter(
            Q(last_sync_at__isnull=True) | Q(last_sync_at__lt=stale_threshold)
        ).count()

        readiness = {
            "products_count": products_count,
            "templates_count": templates_count,
            "barcode_templates_count": barcode_templates_count,
            "stations_total": total_stations,
            "pending_jobs_count": pending_jobs_count,
            "products_without_template": products_without_template,
            "stations_stale_sync": stations_stale_sync,
        }

        # ── NEW: Recent Print Jobs ───────────────────────────────────────────
        recent_jobs_qs = PrintJob.objects.select_related(
            'station', 'nomenclature'
        ).order_by('-created_at')[:5]
        recent_jobs = [
            {
                "id": job.pk,
                "nomenclature_name": job.nomenclature.name if job.nomenclature else "—",
                "station_name": job.station.station_name if job.station else "—",
                "station_number": job.station.station_number if job.station else None,
                "quantity": job.quantity,
                "quantity_unit": job.quantity_unit,
                "status": job.status,
                "created_at": job.created_at.isoformat(),
            }
            for job in recent_jobs_qs
        ]

        # ── NEW: Stations Detail (with mode) ────────────────────────────────
        # Per-station aggregates in ONE grouped query: marked/deleted counts, good + deleted
        # weight (kg), and the activity span (first/last marking) — feeds the per-station modal.
        agg_by_station = {}
        for row in PrintedLabel.objects.values('station').annotate(
            marked=Count('id', filter=Q(is_deleted=False)),
            deleted=Count('id', filter=Q(is_deleted=True)),
            weight_g=Coalesce(Sum(weight_expr, filter=Q(is_deleted=False)), 0.0),
            deleted_weight_g=Coalesce(Sum(weight_expr, filter=Q(is_deleted=True)), 0.0),
            first_at=Min('printed_at'),
            last_at=Max('printed_at'),
        ):
            agg_by_station[row['station']] = row

        stations_detail = []
        for s in LabelsStations.objects.all().order_by('station_number'):
            a = agg_by_station.get(s.pk) or {}
            stations_detail.append({
                "id": s.pk,
                "name": s.station_name,
                "number": s.station_number,
                "uuid": str(s.station_uuid),
                "is_online": s.is_online,
                "mode": s.mode,
                "last_sync_at": s.last_sync_at.isoformat() if s.last_sync_at else None,
                "labels_count": a.get('marked', 0),
                "marked": a.get('marked', 0),
                "deleted": a.get('deleted', 0),
                "weight_kg": round((a.get('weight_g') or 0.0) / 1000.0, 2),
                "deleted_weight_kg": round((a.get('deleted_weight_g') or 0.0) / 1000.0, 2),
                "first_at": a['first_at'].isoformat() if a.get('first_at') else None,
                "last_at": a['last_at'].isoformat() if a.get('last_at') else None,
            })

        # ── NEW: Server Events ───────────────────────────────────────────────
        server_events_qs = ServerEvent.objects.order_by('-created_at')[:10]
        server_events = [
            {
                "id": ev.pk,
                "action": ev.action,
                "action_display": ev.get_action_display(),
                "description": ev.description,
                "created_at": ev.created_at.isoformat(),
            }
            for ev in server_events_qs
        ]

        return Response({
            # Legacy fields
            "total_labels": total_labels,
            "labels_today": labels_today,
            "total_weight_kg": total_weight_kg,
            "weight_today_kg": weight_today_kg,
            "deleted_today": deleted_today,
            "deleted_total": deleted_total,
            "deleted_weight_today_kg": deleted_weight_today_kg,
            "deleted_weight_total_kg": deleted_weight_total_kg,
            "labels_yesterday": labels_yesterday,
            "throughput_24h": throughput_24h,
            "throughput_7d": throughput_7d,
            "top_stations": top_stations,
            "top_products": top_products,
            "recent_logs": recent_logs,
            "active_stations": active_stations,
            "total_stations": total_stations,
            # New fields
            "readiness": readiness,
            "recent_jobs": recent_jobs,
            "stations_detail": stations_detail,
            "server_events": server_events,
        })


class StationLabelsView(APIView):
    """Per-station marking detail — each printed/deleted label (pack) with time, operator,
    product, weight and deletion state. Powers the dashboard's per-station drill-down for full
    traceability. Paginated (limit/offset, newest first) and scopeable (today | all)."""
    permission_classes = [AllowAny]

    def get(self, request):
        station_id = request.query_params.get('station_id')
        scope = request.query_params.get('scope', 'all')
        date_str = request.query_params.get('date')
        try:
            limit = min(max(int(request.query_params.get('limit', 300)), 1), 1000)
        except (TypeError, ValueError):
            limit = 300
        try:
            offset = max(int(request.query_params.get('offset', 0)), 0)
        except (TypeError, ValueError):
            offset = 0

        qs = PrintedLabel.objects.all()
        station = None
        if station_id:
            try:
                station = LabelsStations.objects.filter(pk=int(station_id)).first()
            except (TypeError, ValueError):
                station = None
            qs = qs.filter(station_id=station_id)

        # Day filters bucket by EFFECTIVE activity time (deletion time for deleted rows, else print
        # time), so a pack marked yesterday but deleted today lands on the day it was deleted.
        if date_str:
            from django.utils.dateparse import parse_date
            d = parse_date(date_str)
            if d:
                start = timezone.now().replace(
                    year=d.year, month=d.month, day=d.day, hour=0, minute=0, second=0, microsecond=0
                )
                end = start + datetime.timedelta(days=1)
                qs = qs.annotate(_dt=Coalesce('deleted_at', 'printed_at')).filter(_dt__gte=start, _dt__lt=end)
        elif scope == 'today':
            today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            qs = qs.annotate(_dt=Coalesce('deleted_at', 'printed_at')).filter(_dt__gte=today)

        total = qs.count()
        rows = qs.order_by('-printed_at', '-id')[offset:offset + limit]
        labels = [{
            "id": r.id,
            "pack_name": r.pack_name_snapshot,
            "product_name": r.product_name_snapshot,
            "operator": r.station_user_name,
            "printed_at": r.printed_at.isoformat() if r.printed_at else None,
            "weight_kg": round((r.weight_netto_grams or 0.0) / 1000.0, 3),
            "is_deleted": r.is_deleted,
            "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None,
        } for r in rows]

        return Response({
            "station": ({
                "id": station.pk,
                "name": station.station_name,
                "number": station.station_number,
            } if station else None),
            "total": total,
            "limit": limit,
            "offset": offset,
            "labels": labels,
        })
