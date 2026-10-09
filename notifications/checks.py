"""Periodic checks for conditions nobody reports by themselves: stations gone silent,
seat states, the licence and the vendor seat list nearing expiry, a server update.
Each check raises the condition while it lasts and resolves it once it is gone."""
import datetime
import json
import logging
import urllib.request

from django.conf import settings
from django.utils import timezone

from .service import ensure_notification, purge_old, resolve, resolve_prefix

log = logging.getLogger(__name__)

OFFLINE_AFTER = datetime.timedelta(minutes=10)
STALE_REPORT_AFTER = datetime.timedelta(days=7)
LICENSE_WARN_DAYS = 14
UPDATER_CHECK_URL = "http://127.0.0.1:9000/check"


def last_signal(station):
    """When the station itself was last heard of. `last_seen_at` (set only by its own
    heartbeat) once the server has it; until then `changed_at`, which admin edits move too."""
    return getattr(station, 'last_seen_at', None) or station.changed_at


def check_stations(now=None):
    from label_stations.models import LabelsStations
    from licensing import seats

    now = now or timezone.now()
    seated = seats.seated_ids()
    for station in LabelsStations.objects.all():
        uuid = str(station.station_uuid)
        prefix = f"station:{uuid}:"
        params = {"station": station.station_name, "number": station.station_number}
        link = {"link_tab": "stations", "link_id": uuid}
        state = station.seat_state or seats.SEAT_ACTIVE

        if station.conflict_fingerprint:
            ensure_notification(prefix + "conflict", "station.conflict", "critical", params, **link, now=now)
        else:
            resolve(prefix + "conflict", now)

        if state == seats.SEAT_RELEASED:
            # Not in use: nothing about it is a problem any more.
            resolve_prefix(prefix, keep=[prefix + "conflict"] if station.conflict_fingerprint else (), now=now)
            continue

        if state == seats.SEAT_PENDING:
            ensure_notification(prefix + "pending", "station.pending", "warning", params, **link, now=now)
        else:
            resolve(prefix + "pending", now)

        active = state == seats.SEAT_ACTIVE
        if active and not seats.within_cap(station, seated=seated):
            ensure_notification(prefix + "outside_cap", "station.outside_cap", "critical", params, **link, now=now)
        else:
            resolve(prefix + "outside_cap", now)

        listed = seats.seat_list_state(station) if active else None
        if listed in ("unlisted", "no_list"):
            ensure_notification(prefix + "unlisted", "station.unlisted", "warning", params, **link, now=now)
        else:
            resolve(prefix + "unlisted", now)

        # A station silent because of a computer conflict is that one problem, not two.
        seen = last_signal(station)
        if active and not station.is_online and not station.conflict_fingerprint                 and seen is not None and now - seen >= OFFLINE_AFTER:
            ensure_notification(prefix + "offline", "station.offline", "error",
                                {**params, "since": seen.isoformat()}, **link, now=now)
        elif station.is_online or station.conflict_fingerprint:
            resolve(prefix + "offline", now)

        if active and station.mode in ("offline", "hybrid") and station.last_sync_at is not None \
                and now - station.last_sync_at >= STALE_REPORT_AFTER:
            ensure_notification(prefix + "stale_report", "station.stale_report", "warning",
                                {**params, "last": station.last_sync_at.isoformat()}, **link, now=now)
        else:
            resolve(prefix + "stale_report", now)


def check_license(now=None):
    from licensing.core import license_status

    now = now or timezone.now()
    info = license_status()
    link = {"link_tab": "license"}
    if not info.get("licensed"):
        resolve_prefix("license:", now=now)
        return
    days = info.get("days_left")
    if info.get("expired") and info.get("grace"):
        resolve("license:expiring", now)
        resolve("license:expired", now)
        ensure_notification("license:grace", "license.grace", "critical",
                            {"days": days, "until": info.get("grace_until")}, **link, now=now)
    elif info.get("expired"):
        resolve("license:expiring", now)
        resolve("license:grace", now)
        ensure_notification("license:expired", "license.expired", "critical", {"date": info.get("expires")}, **link, now=now)
    elif days is not None and days <= LICENSE_WARN_DAYS:
        resolve("license:grace", now)
        resolve("license:expired", now)
        ensure_notification("license:expiring", "license.expiring", "warning",
                            {"days": days, "date": info.get("expires")}, **link, now=now)
    else:
        resolve_prefix("license:", now=now)


def check_seat_list(now=None):
    from licensing import seat_list

    now = now or timezone.now()
    status = seat_list.status()
    link = {"link_tab": "license"}
    if not status.get("required"):
        resolve_prefix("seatlist:", now=now)
        return
    if not status.get("present"):
        resolve_prefix("seatlist:", keep=["seatlist:missing"], now=now)
        ensure_notification("seatlist:missing", "seatlist.missing", "critical", {}, **link, now=now)
    elif status.get("expired"):
        resolve_prefix("seatlist:", keep=["seatlist:expired"], now=now)
        ensure_notification("seatlist:expired", "seatlist.expired", "critical", {"date": status.get("expires")}, **link, now=now)
    elif status.get("renewal_due"):
        resolve_prefix("seatlist:", keep=["seatlist:expiring"], now=now)
        ensure_notification("seatlist:expiring", "seatlist.expiring", "warning",
                            {"days": status.get("days_left"), "date": status.get("expires")}, **link, now=now)
    else:
        resolve_prefix("seatlist:", now=now)


def check_server_update(now=None, fetch=None):
    """Ask the local updater service (same machine, port 9000) whether a newer server
    release exists. Absent updater (dev, Docker) = nothing to report."""
    from .versions import is_newer

    now = now or timezone.now()
    try:
        data = fetch() if fetch else _fetch_updater()
    except Exception:
        return
    version = str((data or {}).get("version") or "").strip()
    if (data or {}).get("available") and version and is_newer(version, settings.VERSION):
        key = f"update:server:{version}"
        resolve_prefix("update:server:", keep=[key], now=now)
        ensure_notification(key, "update.server", "info", {"version": version}, link_tab="settings", now=now)
    else:
        resolve_prefix("update:server:", now=now)


def _fetch_updater():
    with urllib.request.urlopen(UPDATER_CHECK_URL, timeout=4) as response:  # noqa: S310 - fixed local URL
        return json.loads(response.read().decode("utf-8"))


def run_all(now=None, include_update=False):
    for check in (check_stations, check_license, check_seat_list):
        try:
            check(now)
        except Exception:
            log.exception("notification check %s failed", check.__name__)
    if include_update:
        try:
            check_server_update(now)
        except Exception:
            log.exception("server update check failed")
    try:
        purge_old(now)
    except Exception:
        log.exception("notification purge failed")
