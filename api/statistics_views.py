from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
from django.db.models import Count, Sum, F, FloatField, Q
from django.db.models.functions import Coalesce, TruncHour, TruncDate
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

        # ── Old metrics (kept for backwards compat) ──────────────────────────
        total_labels = PrintedLabel.objects.count()
        labels_today = PrintedLabel.objects.filter(printed_at__gte=today).count()

        total_weight_agg = PrintedLabel.objects.filter(
            product__is_fixed_weight=True
        ).aggregate(
            total_weight=Coalesce(Sum(F('product__fixed_weight_grams'), output_field=FloatField()), 0.0)
        )
        total_weight_kg = round(total_weight_agg['total_weight'] / 1000.0, 2)

        today_weight_agg = PrintedLabel.objects.filter(
            printed_at__gte=today,
            product__is_fixed_weight=True
        ).aggregate(
            today_weight=Coalesce(Sum(F('product__fixed_weight_grams'), output_field=FloatField()), 0.0)
        )
        weight_today_kg = round(today_weight_agg['today_weight'] / 1000.0, 2)

        # ── Throughput over time + yesterday delta (dashboard charts) ────────
        now = timezone.now()
        yesterday = today - datetime.timedelta(days=1)
        labels_yesterday = PrintedLabel.objects.filter(
            printed_at__gte=yesterday, printed_at__lt=today
        ).count()

        start_24h = (now - datetime.timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
        hourly_map = {
            row['bucket']: row['c']
            for row in PrintedLabel.objects.filter(printed_at__gte=start_24h)
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
            for row in PrintedLabel.objects.filter(printed_at__gte=start_7d)
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
        top_stations_qs = PrintedLabel.objects.values(
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
        top_products_qs = PrintedLabel.objects.values(
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
        stations_detail = []
        for s in LabelsStations.objects.all().order_by('station_number'):
            labels_count = PrintedLabel.objects.filter(station=s).count()
            stations_detail.append({
                "id": s.pk,
                "name": s.station_name,
                "number": s.station_number,
                "uuid": str(s.station_uuid),
                "is_online": s.is_online,
                "mode": s.mode,
                "last_sync_at": s.last_sync_at.isoformat() if s.last_sync_at else None,
                "labels_count": labels_count,
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
