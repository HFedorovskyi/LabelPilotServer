"""Production data for the «Сегодня» page and a station's own page.

Days are the server computer's LOCAL calendar days (the database keeps UTC): a plant in
Germany starts its day at 00:00 local time, not at 02:00. Every view here needs a signed-in
user — the data names operators and weighs every pack.
"""
import csv
import datetime
import io

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import content_disposition_header
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsAdmin
from api.statistics_views import net_weight_expr
from label_stations.models import LabelsStations, SeatEvent
from Nomenclature.models import Nomenclature
from print_jobs.models import PrintJob
from ProductionLogs.models import PrintedContainer, PrintedLabel, ProductionSettings, StationLog

# A pause between two labels longer than this is a stop, not a slow pack.
STOP_AFTER = datetime.timedelta(minutes=10)
# The rate of a line: labels in the last hour.
RATE_WINDOW = datetime.timedelta(hours=1)
FAULT_COMPONENTS = ('printer', 'scale')
MAX_PERIOD_DAYS = 366
LIST_LIMIT = 200


# ── local days ─────────────────────────────────────────────────────────────────────────
def local_today():
    return datetime.datetime.now().astimezone().date()


def day_start(day):
    """Local midnight of a calendar day as an aware datetime (the offset of that very day)."""
    return datetime.datetime.combine(day, datetime.time()).astimezone()


def period_bounds(first, last):
    return day_start(first), day_start(last + datetime.timedelta(days=1))


def local(dt):
    return dt.astimezone() if dt else None


def iso(dt):
    return local(dt).isoformat() if dt else None


def parse_period(request):
    """`from`/`to` (YYYY-MM-DD, local days, inclusive); one day when only one is given."""
    today = local_today()
    first = parse_date(request.query_params.get('from') or '') or today
    last = parse_date(request.query_params.get('to') or '') or first
    if last < first:
        first, last = last, first
    if (last - first).days >= MAX_PERIOD_DAYS:
        first = last - datetime.timedelta(days=MAX_PERIOD_DAYS - 1)
    return first, last


def grams(value):
    return round((value or 0.0) / 1000.0, 3)


# ── shared pieces ──────────────────────────────────────────────────────────────────────
def good_labels(start, end):
    return PrintedLabel.objects.filter(is_deleted=False, printed_at__gte=start, printed_at__lt=end)


def deleted_labels(start, end):
    return (PrintedLabel.objects.filter(is_deleted=True)
            .annotate(_at=Coalesce('deleted_at', 'printed_at')).filter(_at__gte=start, _at__lt=end))


def weighed_rows(qs, *fields):
    """Rows with their net grams (fixed-weight products count their nominal weight)."""
    return qs.annotate(net=net_weight_expr()).values(*fields, 'net')


def open_fault(station_id, last_label_at):
    """The printer or scale error the station reported after its last label: the line has not
    printed since, so it is still standing. A label after the error means it was fixed, and
    so does the station's own all-clear (INFO of that part, stations from 2.0.9)."""
    log = (StationLog.objects.filter(station_id=station_id, level__in=('ERROR', 'CRITICAL'),
                                     component__in=FAULT_COMPONENTS)
           .order_by('-timestamp').first())
    if log is None or (last_label_at and log.timestamp <= last_label_at):
        return None
    if log.timestamp < timezone.now() - datetime.timedelta(hours=12):
        return None
    if StationLog.objects.filter(station_id=station_id, level='INFO', component=log.component,
                                 timestamp__gt=log.timestamp).exists():
        return None
    return {'component': log.component, 'message': log.message, 'since': iso(log.timestamp)}


def job_row(job, rate=None):
    left = max(0.0, (job.quantity or 0) - (job.printed_qty or 0))
    eta = None
    if rate and job.quantity_unit != 'kg' and left > 0:
        eta = round(left / rate * 60)
    return {
        'id': job.id,
        'product': job.nomenclature.name if job.nomenclature_id else '',
        'quantity': job.quantity,
        'unit': job.quantity_unit,
        'printed': job.printed_qty or 0,
        'status': job.status,
        'eta_minutes': eta,
        'completed_at': iso(job.completed_at),
        'created_at': iso(job.created_at),
        'error': job.last_error,
    }


# ── «Сегодня» ──────────────────────────────────────────────────────────────────────────
class ProductionTodayView(APIView):
    def get(self, request):
        now = timezone.now()
        today = local_today()
        start, end = period_bounds(today, today)
        y_start = day_start(today - datetime.timedelta(days=1))
        y_cut = y_start + (now - start)

        rows = list(weighed_rows(good_labels(start, end), 'station_id', 'printed_at', 'product_name_snapshot',
                                 'station_user_name'))
        rows.sort(key=lambda r: r['printed_at'])
        yesterday = list(good_labels(y_start, start).values_list('printed_at', flat=True))
        deleted = list(weighed_rows(deleted_labels(start, end), 'station_id'))

        hourly = [0] * 24
        hourly_prev = [0] * 24
        for r in rows:
            hourly[local(r['printed_at']).hour] += 1
        for at in yesterday:
            hourly_prev[local(at).hour] += 1

        products = {}
        lines = {}
        for r in rows:
            p = products.setdefault(r['product_name_snapshot'] or '—', {'pcs': 0, 'grams': 0.0})
            p['pcs'] += 1
            p['grams'] += r['net'] or 0.0
            if r['station_id'] is None:
                continue
            line = lines.setdefault(r['station_id'], {'labels': 0, 'grams': 0.0, 'hourly': [0] * 24, 'last': None, 'rate': 0})
            line['labels'] += 1
            line['grams'] += r['net'] or 0.0
            line['hourly'][local(r['printed_at']).hour] += 1
            line['last'] = r
            if r['printed_at'] >= now - RATE_WINDOW:
                line['rate'] += 1

        active_jobs = {}
        for job in (PrintJob.objects.select_related('nomenclature').filter(status='sent').order_by('-sent_at', '-id')):
            active_jobs.setdefault(job.station_id, job)

        stations = []
        for s in LabelsStations.objects.exclude(seat_state='released').order_by('station_name'):
            line = lines.get(s.id, {'labels': 0, 'grams': 0.0, 'hourly': [0] * 24, 'last': None, 'rate': 0})
            last = line['last']
            job = active_jobs.get(s.id)
            stations.append({
                'id': s.id,
                'uuid': str(s.station_uuid),
                'name': s.station_name,
                'number': s.station_number,
                'online': bool(s.is_online),
                'seen_at': iso(s.changed_at),
                'labels': line['labels'],
                'kg': grams(line['grams']),
                'hourly': line['hourly'],
                'rate': line['rate'],
                'last_at': iso(last['printed_at']) if last else None,
                'last_product': last['product_name_snapshot'] if last else '',
                'operator': last['station_user_name'] if last else '',
                'job': job_row(job, line['rate']) if job else None,
                'fault': open_fault(s.id, last['printed_at'] if last else None),
            })

        todays_jobs = PrintJob.objects.select_related('nomenclature').filter(
            Q(created_at__gte=start) | Q(completed_at__gte=start) | Q(status__in=('pending', 'sent', 'error')))
        fractions = [min(1.0, (j.printed_qty or 0) / j.quantity) if j.status != 'completed' and j.quantity else 1.0
                     for j in todays_jobs]
        failed = [job_row(j) for j in todays_jobs if j.status == 'error']

        # The last 7 days and the 7 before them, for the chart's «7 дней».
        w_start = day_start(today - datetime.timedelta(days=13))
        week = {}
        for at in good_labels(w_start, end).values_list('printed_at', flat=True):
            day = local(at).date()
            week[day] = week.get(day, 0) + 1
        days7 = [today - datetime.timedelta(days=6 - i) for i in range(7)]

        return Response({
            'date': today.isoformat(),
            'now': iso(now),
            'week': [{'date': d.isoformat(), 'count': week.get(d, 0),
                      'previous': week.get(d - datetime.timedelta(days=7), 0)} for d in days7],
            'totals': {
                'labels': len(rows),
                'kg': grams(sum(r['net'] or 0.0 for r in rows)),
                'deleted': len(deleted),
                'deleted_kg': grams(sum(r['net'] or 0.0 for r in deleted)),
                'yesterday_same_time': sum(1 for at in yesterday if at < y_cut),
            },
            'hourly': hourly,
            'hourly_yesterday': hourly_prev,
            'stations': stations,
            'jobs': {
                'in_progress': sum(1 for j in todays_jobs if j.status == 'sent'),
                'waiting': sum(1 for j in todays_jobs if j.status == 'pending'),
                'done': sum(1 for j in todays_jobs if j.status == 'completed'),
                'failed': failed,
                'percent': round(sum(fractions) / len(fractions) * 100) if fractions else None,
            },
            'products': sorted(({'name': name, 'pcs': v['pcs'], 'kg': grams(v['grams'])} for name, v in products.items()),
                               key=lambda p: -p['pcs']),
            'setup': {
                'products': Nomenclature.objects.count(),
                # A station refuses a pack without a pack label template.
                'products_without_template': Nomenclature.objects.filter(templates_pack_label__isnull=True).count(),
                'stations': LabelsStations.objects.count(),
            },
        })


# ── a station's page ───────────────────────────────────────────────────────────────────
def station_or_404(uuid):
    return get_object_or_404(LabelsStations, station_uuid=uuid)


class StationStatsView(APIView):
    """Totals, chart, products, operators, jobs and working time for one day or a period."""

    def get(self, request, uuid):
        station = station_or_404(uuid)
        first, last = parse_period(request)
        start, end = period_bounds(first, last)
        single = first == last
        days = (last - first).days + 1
        # Compared with: the same weekday a week earlier (one day) or the period just before.
        shift = datetime.timedelta(days=7 if single else days)
        p_start, p_end = period_bounds(first - shift, last - shift)
        now = timezone.now()
        running = start <= now < end
        if running:  # today is not over: compare with the same point of the earlier period
            p_end = min(p_end, now - shift)

        operator_output = ProductionSettings.current().operator_output
        rows = list(weighed_rows(good_labels(start, end).filter(station=station), 'printed_at',
                                 'product_name_snapshot', 'station_user_name'))
        rows.sort(key=lambda r: r['printed_at'])
        deleted = list(weighed_rows(deleted_labels(start, end).filter(station=station), 'printed_at'))
        previous = good_labels(p_start, p_end).filter(station=station).count()
        total_grams = sum(r['net'] or 0.0 for r in rows)

        if single:
            series = [{'label': f'{h:02d}', 'count': 0} for h in range(24)]
            for r in rows:
                series[local(r['printed_at']).hour]['count'] += 1
        else:
            index = {first + datetime.timedelta(days=i): i for i in range(days)}
            series = [{'label': d.isoformat(), 'count': 0} for d in index]
            for r in rows:
                series[index[local(r['printed_at']).date()]]['count'] += 1

        products, operators = {}, {}
        for r in rows:
            p = products.setdefault(r['product_name_snapshot'] or '—', {'pcs': 0, 'grams': 0.0})
            p['pcs'] += 1
            p['grams'] += r['net'] or 0.0
            o = operators.setdefault(r['station_user_name'] or '—', {'pcs': 0, 'grams': 0.0, 'first': r['printed_at'],
                                                                     'last': r['printed_at'], 'days': set()})
            o['pcs'] += 1
            o['grams'] += r['net'] or 0.0
            o['last'] = r['printed_at']
            o['days'].add(local(r['printed_at']).date())

        in_period = Q(created_at__gte=start, created_at__lt=end) | Q(completed_at__gte=start, completed_at__lt=end)
        if running:
            in_period |= Q(status='sent')
        jobs = PrintJob.objects.select_related('nomenclature').filter(station=station).filter(in_period).order_by('-created_at')[:50]
        last_label_at = (PrintedLabel.objects.filter(station=station, is_deleted=False)
                         .order_by('-printed_at').values_list('printed_at', flat=True).first())
        containers = PrintedContainer.objects.filter(station=station, is_deleted=False, opened_at__gte=start, opened_at__lt=end)

        return Response({
            'from': first.isoformat(),
            'to': last.isoformat(),
            'single_day': single,
            'totals': {
                'labels': len(rows),
                'kg': grams(total_grams),
                'avg_kg': grams(total_grams / len(rows)) if rows else None,
                'deleted': len(deleted),
                'deleted_kg': grams(sum(r['net'] or 0.0 for r in deleted)),
                'previous_labels': previous,
                'boxes': containers.filter(level='box').count(),
                'pallets': containers.filter(level='pallet').count(),
            },
            'series': series,
            'work': work_time(station, rows, start, end, single),
            'products': sorted(({'name': name, 'pcs': v['pcs'], 'kg': grams(v['grams']),
                                 'avg_kg': grams(v['grams'] / v['pcs'])} for name, v in products.items()),
                               key=lambda p: -p['pcs']),
            # Output per person only where the admin has enabled it (see ProductionSettings).
            'operators': sorted(({'name': name, 'pcs': v['pcs'], 'kg': grams(v['grams']), 'first': iso(v['first']),
                                  'last': iso(v['last']), 'days': len(v['days'])} for name, v in operators.items()),
                                key=lambda o: -o['pcs']) if operator_output else [],
            'operator_output': operator_output,
            'jobs': [job_row(j) for j in jobs],
            # The printer or scale error the line is standing on right now (any period).
            'fault': open_fault(station.id, last_label_at),
        })


def work_time(station, rows, start, end, single):
    """When the station worked: first/last label, stops between labels (with the printer or
    scale error that explains one), and for a period the average working day."""
    if not rows:
        return {'first': None, 'last': None, 'minutes': 0, 'stops': [], 'days_worked': 0}
    by_day = {}
    for r in rows:
        by_day.setdefault(local(r['printed_at']).date(), []).append(r['printed_at'])
    day_minutes = [(times[-1] - times[0]).total_seconds() / 60 for times in by_day.values()]
    stops = []
    until = None
    if single:
        faults = list(StationLog.objects.filter(station=station, timestamp__gte=start, timestamp__lt=end,
                                                level__in=('ERROR', 'CRITICAL'), component__in=FAULT_COMPONENTS)
                      .order_by('timestamp').values('timestamp', 'component', 'message'))
        times = [r['printed_at'] for r in rows]
        now = timezone.now()
        # Today the line may be standing right now: that stop runs from its last label to now.
        ends = times[1:] + ([now] if start <= now < end and now - times[-1] >= STOP_AFTER else [])
        for a, b in zip(times, ends):
            if b - a >= STOP_AFTER:
                cause = next((f for f in faults if a <= f['timestamp'] <= b), None)
                stops.append({'from': iso(a), 'to': iso(b), 'minutes': round((b - a).total_seconds() / 60),
                              'kind': 'fault' if cause else 'idle',
                              'reason': cause['message'] if cause else '', 'ongoing': b is now})
        if len(ends) == len(times):
            until = iso(now)
    inside = sum(s['minutes'] for s in stops if not s.get('ongoing'))
    return {
        'first': iso(rows[0]['printed_at']),
        'last': iso(rows[-1]['printed_at']),
        # The timeline's right edge: now while today's line stands, else the last label.
        'until': until,
        'minutes': round(sum(day_minutes) / len(day_minutes)) - (inside if single else 0),
        'stopped_minutes': sum(s['minutes'] for s in stops),
        'stops': stops,
        'days_worked': len(by_day),
    }


class StationDaysView(APIView):
    """Local days of a month on which the station printed (dots in the calendar)."""

    def get(self, request, uuid):
        station = station_or_404(uuid)
        month = parse_date((request.query_params.get('month') or '') + '-01') or local_today().replace(day=1)
        month = month.replace(day=1)
        following = (month + datetime.timedelta(days=32)).replace(day=1)
        start, end = day_start(month), day_start(following)
        days = {local(at).date().isoformat()
                for at in good_labels(start, end).filter(station=station).values_list('printed_at', flat=True)}
        return Response({'month': month.isoformat()[:7], 'days': sorted(days)})


LABEL_COLUMNS = {
    'pack': ['Время', 'Товар', 'Нетто, кг', 'Брутто, кг', 'Партия', 'Оператор', 'Штрихкод', 'Короб', 'Удалена'],
    'box': ['Открыт', 'Закрыт', 'Короб', 'Товар', 'Упаковок', 'Нетто, кг', 'Брутто, кг', 'Паллета', 'Удалён'],
    'pallet': ['Открыта', 'Закрыта', 'Паллета', 'Товары', 'Коробов', 'Упаковок', 'Нетто, кг', 'Брутто, кг'],
}


class StationLabelsPeriodView(APIView):
    """Every pack, box or pallet of the station in a period: search, «only deleted», pages, CSV."""

    def get(self, request, uuid):
        station = station_or_404(uuid)
        first, last = parse_period(request)
        start, end = period_bounds(first, last)
        level = request.query_params.get('level') or 'pack'
        query = (request.query_params.get('q') or '').strip()
        only_deleted = request.query_params.get('deleted') in ('1', 'true')
        try:
            offset = max(int(request.query_params.get('offset', 0)), 0)
            limit = min(max(int(request.query_params.get('limit', 50)), 1), LIST_LIMIT)
        except ValueError:
            offset, limit = 0, 50
        # Not «format»: DRF reads that one to pick a renderer.
        as_csv = request.query_params.get('export') == 'csv'

        packs = (PrintedLabel.objects.filter(station=station)
                 .annotate(_at=Coalesce('deleted_at', 'printed_at')).filter(_at__gte=start, _at__lt=end))
        containers = PrintedContainer.objects.filter(station=station, opened_at__gte=start, opened_at__lt=end)
        counts = {
            'pack': packs.filter(is_deleted=False).count(),
            'box': containers.filter(level='box', is_deleted=False).count(),
            'pallet': containers.filter(level='pallet', is_deleted=False).count(),
        }
        if level == 'pack':
            qs = packs
            if query:
                qs = qs.filter(Q(product_name_snapshot__icontains=query) | Q(barcode__icontains=query)
                               | Q(batch__icontains=query) | Q(station_user_name__icontains=query)
                               | Q(box_number__icontains=query))
            deleted_total = qs.filter(is_deleted=True).count()
            if only_deleted:
                qs = qs.filter(is_deleted=True)
            qs = qs.select_related('product').annotate(net=net_weight_expr()).order_by('-printed_at', '-id')
            rows = [{
                'id': r.id, 'at': iso(r.printed_at), 'product': r.product_name_snapshot, 'kg': grams(r.net),
                'gross_kg': grams(r.weight_brutto_grams) if r.weight_brutto_grams else None,
                'batch': r.batch, 'operator': r.station_user_name, 'barcode': r.barcode,
                'box': r.box_number, 'deleted': r.is_deleted, 'deleted_at': iso(r.deleted_at),
            } for r in (qs if as_csv else qs[offset:offset + limit])]
            total = qs.count()
        else:
            qs = containers.filter(level='pallet' if level == 'pallet' else 'box')
            if query:
                qs = qs.filter(Q(number__icontains=query) | Q(product_name_snapshot__icontains=query)
                               | Q(parent_number__icontains=query))
            deleted_total = qs.filter(is_deleted=True).count()
            if only_deleted:
                qs = qs.filter(is_deleted=True)
            qs = qs.order_by('-opened_at', '-id')
            rows = [{
                'id': c.id, 'opened_at': iso(c.opened_at), 'closed_at': iso(c.closed_at), 'closed': c.is_closed,
                'number': c.number, 'product': c.product_name_snapshot, 'packs': c.packs_count,
                'boxes': c.boxes_count, 'capacity': c.capacity, 'kg': grams(c.weight_netto_grams),
                'gross_kg': grams(c.weight_brutto_grams), 'pallet': c.parent_number,
                'deleted': c.is_deleted, 'deleted_at': iso(c.deleted_at),
            } for c in (qs if as_csv else qs[offset:offset + limit])]
            total = qs.count()

        if as_csv:
            return labels_csv(station, level, first, last, rows)
        return Response({'level': level, 'counts': counts, 'total': total, 'deleted': deleted_total,
                         'offset': offset, 'rows': rows})


def labels_csv(station, level, first, last, rows):
    out = io.StringIO()
    out.write('﻿')  # Excel opens UTF-8 with a BOM
    writer = csv.writer(out, delimiter=';')
    writer.writerow(LABEL_COLUMNS.get(level, LABEL_COLUMNS['pack']))
    when = lambda value: local(datetime.datetime.fromisoformat(value)).strftime('%d.%m.%Y %H:%M:%S') if value else ''  # noqa: E731
    num = lambda value: '' if value is None else str(value).replace('.', ',')  # noqa: E731
    for r in rows:
        if level == 'pack':
            writer.writerow([when(r['at']), r['product'], num(r['kg']), num(r['gross_kg']), r['batch'], r['operator'],
                             r['barcode'], r['box'], when(r['deleted_at']) if r['deleted'] else ''])
        elif level == 'box':
            writer.writerow([when(r['opened_at']), when(r['closed_at']), r['number'], r['product'], r['packs'],
                             num(r['kg']), num(r['gross_kg']), r['pallet'], when(r['deleted_at']) if r['deleted'] else ''])
        else:
            writer.writerow([when(r['opened_at']), when(r['closed_at']), r['number'], r['product'], r['boxes'],
                             r['packs'], num(r['kg']), num(r['gross_kg'])])
    name = f"{station.station_name}_{level}_{first.isoformat()}" + ('' if first == last else f"_{last.isoformat()}")
    response = HttpResponse(out.getvalue(), content_type='text/csv; charset=utf-8')
    # filename* keeps a Cyrillic station name readable (RFC 6266); others get an ASCII fallback.
    response['Content-Disposition'] = content_disposition_header(
        True, ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in name) + '.csv')
    return response


class StationJournalView(APIView):
    """What happened at the station in a period: its log (errors, printer, scale…) and the
    seat events, newest first."""

    def get(self, request, uuid):
        station = station_or_404(uuid)
        first, last = parse_period(request)
        start, end = period_bounds(first, last)
        kind = request.query_params.get('kind') or 'all'
        logs = StationLog.objects.filter(station=station, timestamp__gte=start, timestamp__lt=end)
        counts = {
            'errors': logs.filter(level__in=('ERROR', 'CRITICAL')).count(),
            'printer': logs.filter(component='printer').count(),
            'scale': logs.filter(component='scale').count(),
        }
        seat = SeatEvent.objects.filter(station=station, created_at__gte=start, created_at__lt=end)
        counts['seat'] = seat.count()
        events = []
        if kind != 'seat':
            if kind == 'errors':
                logs = logs.filter(level__in=('ERROR', 'CRITICAL'))
            elif kind in ('printer', 'scale'):
                logs = logs.filter(component=kind)
            events += [{'at': iso(l.timestamp), 'level': l.level, 'component': l.component or 'app', 'message': l.message}
                       for l in logs.order_by('-timestamp')[:500]]
        if kind in ('all', 'seat'):
            events += [{'at': iso(e.created_at), 'level': 'INFO', 'component': 'seat', 'message': e.event,
                        'detail': e.detail, 'actor': e.actor} for e in seat.order_by('-created_at')[:200]]
        events.sort(key=lambda e: e['at'], reverse=True)
        return Response({'counts': counts, 'events': events[:500]})


# ── boxes and pallets from a station report ───────────────────────────────────────────
def store_containers(station, data):
    """Upsert the boxes and pallets a report carries (stations from 2.0.9)."""
    from django.utils.dateparse import parse_datetime
    items = [('box', it) for it in data.get('boxes') or []] + [('pallet', it) for it in data.get('pallets') or []]
    items = [(level, it) for level, it in items if it.get('unique_id') and it.get('number')]
    if not items:
        return 0
    products = Nomenclature.objects.in_bulk({it['product_id'] for _, it in items if it.get('product_id')})
    for level, it in items:
        product = products.get(it.get('product_id'))
        opened = parse_datetime(it.get('opened_at') or '') or timezone.now()
        PrintedContainer.objects.update_or_create(unique_id=it['unique_id'], defaults={
            'station': station,
            'level': level,
            'number': str(it['number'])[:64],
            'product': product,
            'product_name_snapshot': (it.get('product_name') or (product.name if product else ''))[:255],
            'parent_number': str(it.get('pallet_number') or '')[:64],
            'packs_count': max(int(it.get('packs') or 0), 0),
            'boxes_count': max(int(it.get('boxes') or 0), 0),
            'capacity': it.get('capacity') or None,
            'weight_netto_grams': it.get('weight_netto_grams'),
            'weight_brutto_grams': it.get('weight_brutto_grams'),
            'is_closed': bool(it.get('closed_at')),
            'opened_at': opened,
            'closed_at': parse_datetime(it.get('closed_at') or '') if it.get('closed_at') else None,
            'is_deleted': bool(it.get('deleted_at')),
            'deleted_at': parse_datetime(it.get('deleted_at') or '') if it.get('deleted_at') else None,
        })
    return len(items)


class ProductionSettingsView(APIView):
    """Whether the station page shows output per operator; everyone reads, admins change."""

    def get_permissions(self):
        return [IsAdmin()] if self.request.method == 'PUT' else super().get_permissions()

    def get(self, request):
        return Response({'operator_output': ProductionSettings.current().operator_output})

    def put(self, request):
        settings = ProductionSettings.current()
        settings.operator_output = bool(request.data.get('operator_output'))
        settings.save(update_fields=['operator_output', 'updated_at'])
        return Response({'operator_output': settings.operator_output})
