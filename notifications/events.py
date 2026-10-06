"""Domain events that raise or resolve notifications, called from the API views.
Titles are not built here: the frontend renders `code` + `params` per language."""
from django.conf import settings
from django.utils import timezone

from .service import ensure_notification, message_key, raise_notification, resolve
from .versions import is_newer

ERROR_LEVELS = ('ERROR', 'CRITICAL')


def _station_params(station):
    if station is None:
        return {"station": "", "number": None}
    return {"station": station.station_name, "number": station.station_number}


def _station_link(station):
    return {"link_tab": "stations", "link_id": str(station.station_uuid) if station else ""}


def station_errors(station, logs):
    """Every ERROR a station reports becomes a notification; the same message from the
    same subsystem repeats into one (count + time) instead of flooding the list."""
    uuid = str(station.station_uuid) if station else "unknown"
    for entry in logs:
        if str(entry.get('level', '')).upper() not in ERROR_LEVELS:
            continue
        component = str(entry.get('component') or 'app')[:32]
        message = str(entry.get('message') or '')[:500]
        raise_notification(
            f"station:{uuid}:error:{component}:{message_key(message)}",
            "station.error", "error",
            {**_station_params(station), "component": component, "message": message},
            **_station_link(station),
        )


def station_seen(station, conflict=False):
    """Called on every heartbeat: a conflicting device raises the critical notice at once
    (not a minute later); a genuine signal ends "offline"."""
    key = f"station:{station.station_uuid}:"
    if conflict:
        ensure_notification(key + "conflict", "station.conflict", "critical", _station_params(station), **_station_link(station))
    else:
        resolve(key + "offline")


def station_push(station, error=None):
    key = f"station:{station.station_uuid}:push_failed"
    if error:
        raise_notification(key, "station.push_failed", "error",
                           {**_station_params(station), "error": str(error)[:300]}, **_station_link(station))
    else:
        resolve(key)


def job_send(job, error=None):
    key = f"job:{job.pk}:send"
    if error:
        raise_notification(key, "job.send_failed", "error", {
            "job": job.pk,
            "product": job.nomenclature.name if job.nomenclature_id else "",
            "station": job.station.station_name if job.station_id else "",
            "error": str(error)[:300],
        }, link_tab="print_tasks", link_id=job.pk)
    else:
        resolve(key)


def job_progress(station, items):
    """Apply the progress a station reports for its print jobs. Progress only grows and
    a completed job stays completed; completion raises a quiet info notification."""
    from print_jobs.models import PrintJob

    now = timezone.now()
    ids = [it.get('job_id') for it in items if isinstance(it.get('job_id'), int)]
    jobs = {job.pk: job for job in PrintJob.objects.filter(pk__in=ids).select_related('nomenclature', 'station')}
    updated = 0
    for it in items:
        job = jobs.get(it.get('job_id'))
        if job is None or (station is not None and job.station_id not in (None, station.pk)):
            continue
        try:
            printed = max(float(it.get('printed_qty') or 0), job.printed_qty)
        except (TypeError, ValueError):
            continue
        done = str(it.get('status') or '') == 'completed'
        fields = []
        if printed != job.printed_qty:
            job.printed_qty, job.progress_at = printed, now
            fields += ['printed_qty', 'progress_at']
        if done and job.status != 'completed':
            job.status = 'completed'
            job.completed_at = now
            fields += ['status', 'completed_at']
            raise_notification(f"job:{job.pk}:completed", "job.completed", "info", {
                "job": job.pk, "product": job.nomenclature.name if job.nomenclature_id else "",
                "station": job.station.station_name if job.station_id else "",
                "qty": job.quantity, "unit": job.quantity_unit,
            }, link_tab="print_tasks", link_id=job.pk)
        if fields:
            job.save(update_fields=fields + ['updated_at'])
            updated += 1
    return updated


def client_version(station, version):
    """A station below MIN_CLIENT_VERSION cannot be served correctly (error); an older
    one than LATEST_CLIENT_VERSION just has an update waiting (info)."""
    if station is None or not version:
        return
    key = f"station:{station.station_uuid}:client_outdated"
    minimum = getattr(settings, 'MIN_CLIENT_VERSION', '')
    latest = getattr(settings, 'LATEST_CLIENT_VERSION', '')
    if minimum and is_newer(minimum, version):
        ensure_notification(key, "station.client_outdated", "error",
                            {**_station_params(station), "version": version, "minimum": minimum}, **_station_link(station))
    else:
        resolve(key)
    if latest and is_newer(latest, version):
        ensure_notification(f"update:client:{latest}", "update.client", "info", {"version": latest}, link_tab="stations")


def report_rejected(remote_addr):
    """A report that failed decryption: someone sends data with a foreign key (copied or
    tampered station, or another server's station)."""
    raise_notification(f"report:invalid:{remote_addr or 'unknown'}", "station.report_invalid", "critical",
                       {"ip": remote_addr or ""}, link_tab="stations")
