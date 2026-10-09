"""Named workstation seats.

A station holds a seat from registration until an administrator releases it.
The licence's ``max_stations`` caps the number of ACTIVE seats; stations over
the cap are registered as ``pending`` and receive no data. Releases (including
deleting an active station and confirming replaced hardware) are rate limited
so seats cannot rotate between more physical stations than were purchased.

Station identity is additionally bound to a hardware fingerprint sent by the
client (32 lowercase hex). A second device announcing the same station UUID
is recorded as a conflict and never takes over the station's address.

The cap is enforced again at every data export from the licence itself, not
from the stored seat state: only the first ``max_stations`` active stations in
seat order (who got a seat first keeps it) receive data. Marking more stations
"active" in the database therefore gains nothing.

A licence with the "seat-list" feature adds a vendor-signed list of the
stations' fingerprints (licensing/seat_list.py): a station outside the list
receives no data here, and the stations enforce the same list themselves.

Nothing here stops a working station: a lapsed or reduced licence blocks new
seats and new data for stations beyond the cap; every station keeps printing
with the data it already has.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

SEAT_ACTIVE = "active"
SEAT_PENDING = "pending"
SEAT_RELEASED = "released"

RELEASE_WINDOW = datetime.timedelta(days=30)
MIN_RELEASES_PER_WINDOW = 2
MAX_PENDING_STATIONS = 50

FINGERPRINT_LEGACY = "legacy"      # client did not send a fingerprint (pre-2.0.6)
FINGERPRINT_MATCH = "match"
FINGERPRINT_CONFLICT = "conflict"

_FINGERPRINT_RE = re.compile(r"[0-9a-f]{32}\Z")

# Events that free a seat and count against the release allowance.
_RELEASE_EVENTS = ("released", "deleted", "hardware_replaced")


class SeatError(Exception):
    """A seat operation the licence does not allow. ``code`` maps to an i18n key."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SeatPolicy:
    limit: Optional[int]   # None = no cap (unlimited licence, or demo without a licence)
    can_assign: bool       # False when a present licence is invalid / expired / foreign
    licensed: bool


def valid_fingerprint(value) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if _FINGERPRINT_RE.fullmatch(value) else None


def seat_policy() -> SeatPolicy:
    from .core import license_state

    state = license_state()
    if not state.present:
        # Demo: prospects may register any number of stations; the commercial
        # export gate (not a seat cap) keeps real data from reaching them.
        return SeatPolicy(limit=None, can_assign=True, licensed=False)
    if not state.valid_for_key or state.past_grace or not state.machine_ok:
        return SeatPolicy(limit=0, can_assign=False, licensed=False)
    return SeatPolicy(limit=state.license.max_stations, can_assign=True, licensed=True)


def _stations():
    from label_stations.models import LabelsStations

    return LabelsStations.objects


def active_count() -> int:
    return _stations().filter(seat_state=SEAT_ACTIVE).count()


def seat_available(policy: Optional[SeatPolicy] = None) -> bool:
    policy = policy or seat_policy()
    if not policy.can_assign:
        return False
    return policy.limit is None or active_count() < policy.limit


def release_allowance(policy: Optional[SeatPolicy] = None) -> Optional[int]:
    """Releases allowed per window; None = unrestricted (no seat cap)."""
    policy = policy or seat_policy()
    if policy.limit is None:
        return None
    return max(MIN_RELEASES_PER_WINDOW, policy.limit)


def releases_in_window(now=None) -> int:
    from label_stations.models import SeatEvent

    since = (now or timezone.now()) - RELEASE_WINDOW
    return SeatEvent.objects.filter(event__in=_RELEASE_EVENTS, created_at__gte=since).count()


def _ensure_release_allowed(policy: SeatPolicy) -> None:
    allowance = release_allowance(policy)
    if allowance is not None and releases_in_window() >= allowance:
        raise SeatError("station.seatReleaseLimit")


def _log(station, event: str, actor: str = "", detail: str = "") -> None:
    from label_stations.models import SeatEvent

    SeatEvent.objects.create(
        station=station,
        station_uuid=getattr(station, "station_uuid", None),
        station_name=getattr(station, "station_name", "")[:100],
        event=event,
        actor=(actor or "")[:150],
        detail=(detail or "")[:255],
    )


def _seats_changed() -> None:
    """Ask the vendor for a fresh seat list once the change is committed."""
    def notify():
        try:
            from .seat_list import schedule_sync
            schedule_sync()
        except Exception:
            pass
    transaction.on_commit(notify)


def initial_state() -> Optional[str]:
    """Seat state for a newly registered station, or None when even a pending
    registration must be refused (too many stations already waiting)."""
    policy = seat_policy()
    if seat_available(policy):
        return SEAT_ACTIVE
    if _stations().filter(seat_state=SEAT_PENDING).count() >= MAX_PENDING_STATIONS:
        return None
    return SEAT_PENDING


def record_registration(station, actor: str = "") -> None:
    _log(station, "assigned" if station.seat_state == SEAT_ACTIVE else "pending", actor)
    _seats_changed()


@transaction.atomic
def activate(station, actor: str = "") -> None:
    station = _stations().select_for_update().get(pk=station.pk)
    if station.seat_state == SEAT_ACTIVE:
        return
    if not seat_available():
        raise SeatError("station.seatLimitReached")
    station.seat_state = SEAT_ACTIVE
    station.seat_changed_at = timezone.now()
    station.save(update_fields=["seat_state", "seat_changed_at", "changed_at"])
    _log(station, "assigned", actor)
    _seats_changed()


@transaction.atomic
def release(station, actor: str = "") -> None:
    station = _stations().select_for_update().get(pk=station.pk)
    if station.seat_state != SEAT_ACTIVE:
        return
    _ensure_release_allowed(seat_policy())
    station.seat_state = SEAT_RELEASED
    station.is_online = False
    station.seat_changed_at = timezone.now()
    station.save(update_fields=["seat_state", "is_online", "seat_changed_at", "changed_at"])
    _log(station, "released", actor)
    _seats_changed()


@transaction.atomic
def delete(station, actor: str = "") -> None:
    """Deleting an active station frees its seat, so it spends a release."""
    station = _stations().select_for_update().get(pk=station.pk)
    if station.seat_state == SEAT_ACTIVE:
        _ensure_release_allowed(seat_policy())
        _log(station, "deleted", actor)
        _seats_changed()
    station.delete()


def observe_fingerprint(station, fingerprint, source: str) -> str:
    """Bind the first fingerprint a station reports; flag any other device that
    reuses the station's identity. Returns legacy / match / conflict."""
    fingerprint = valid_fingerprint(fingerprint)
    if fingerprint is None:
        return FINGERPRINT_LEGACY
    if not station.station_fingerprint:
        station.station_fingerprint = fingerprint
        station.save(update_fields=["station_fingerprint", "changed_at"])
        _log(station, "fingerprint_bound", detail=source)
        _seats_changed()
        return FINGERPRINT_MATCH
    if station.station_fingerprint == fingerprint:
        return FINGERPRINT_MATCH
    if station.conflict_fingerprint != fingerprint:
        station.conflict_fingerprint = fingerprint
        station.save(update_fields=["conflict_fingerprint", "changed_at"])
        _log(station, "fingerprint_conflict", detail=f"{source}:{fingerprint[:8]}")
    return FINGERPRINT_CONFLICT


@transaction.atomic
def replace_hardware(station, actor: str = "") -> None:
    """Accept the device that reported a conflicting fingerprint as the
    station's new hardware. The seat moves to it and spends a release."""
    station = _stations().select_for_update().get(pk=station.pk)
    if not station.conflict_fingerprint:
        raise SeatError("station.noHardwareConflict")
    if station.seat_state == SEAT_ACTIVE:
        _ensure_release_allowed(seat_policy())
    previous = station.station_fingerprint[:8]
    station.station_fingerprint = station.conflict_fingerprint
    station.conflict_fingerprint = ""
    station.seat_changed_at = timezone.now()
    station.save(update_fields=["station_fingerprint", "conflict_fingerprint", "seat_changed_at", "changed_at"])
    _log(station, "hardware_replaced", actor, detail=f"{previous}->{station.station_fingerprint[:8]}")
    _seats_changed()


def seated_ids(policy: Optional[SeatPolicy] = None) -> Optional[set]:
    """Primary keys of the active stations inside the licence's seat cap, in seat
    order; None = no cap. Computed from the licence on every call."""
    from django.db.models.functions import Coalesce

    policy = policy or seat_policy()
    if policy.limit is None:
        return None
    ordered = (
        _stations().filter(seat_state=SEAT_ACTIVE)
        .annotate(seat_order=Coalesce("seat_changed_at", "created_at"))
        .order_by("seat_order", "pk")
        .values_list("pk", flat=True)
    )
    return set(ordered[: max(0, policy.limit)])


def within_cap(station, policy: Optional[SeatPolicy] = None, seated: Optional[set] = None) -> bool:
    """An active station inside the seat cap. ``seated`` lets list views compute
    the cap once for many stations."""
    if station is None or station.seat_state != SEAT_ACTIVE:
        return False
    if seated is None:
        seated = seated_ids(policy)
    return seated is None or station.pk in seated


def may_receive_data(station) -> bool:
    try:
        ensure_may_receive_data(station)
    except SeatError:
        return False
    return True


def seat_list_state(station) -> Optional[str]:
    """listed / unlisted / no_list (no valid vendor list on this server);
    None when the licence uses no seat list."""
    from .seat_list import required, valid_list

    if not required():
        return None
    value = valid_list()
    if value is None:
        return "no_list"
    return "listed" if value.lists(station.station_fingerprint or "") else "unlisted"


def ensure_may_receive_data(station) -> None:
    if station is None or station.seat_state != SEAT_ACTIVE:
        raise SeatError("station.seatNotActive")
    if not within_cap(station):
        raise SeatError("station.seatOverLimit")
    from .seat_list import station_listed
    if not station_listed(station):
        raise SeatError("station.notInSeatList")


def station_seat(station, fingerprint_status: Optional[str] = None) -> dict:
    """Seat facts a station shows to its operator (ping response)."""
    policy = seat_policy()
    state = station.seat_state
    if state == SEAT_ACTIVE and not within_cap(station, policy):
        # Shown on the station as "waiting for a seat": it gets no new data.
        state = SEAT_PENDING
    return {
        "state": state,
        "fingerprint": fingerprint_status
        or (FINGERPRINT_MATCH if station.station_fingerprint else FINGERPRINT_LEGACY),
        "used": active_count(),
        "limit": policy.limit,
        "seat_list": seat_list_state(station),
    }


def summary() -> dict:
    """Seat usage for the licence screen and the vendor heartbeat."""
    policy = seat_policy()
    stations = _stations()
    active = stations.filter(seat_state=SEAT_ACTIVE).count()
    return {
        "limit": policy.limit,
        "active": active,
        "pending": stations.filter(seat_state=SEAT_PENDING).count(),
        "released": stations.filter(seat_state=SEAT_RELEASED).count(),
        "fingerprinted": stations.exclude(station_fingerprint="").count(),
        "conflicts": stations.exclude(conflict_fingerprint="").count(),
        "over_limit": policy.limit is not None and active > policy.limit,
        "outside_cap": max(0, active - policy.limit) if policy.limit is not None else 0,
        "releases_30d": releases_in_window(),
        "release_allowance": release_allowance(policy),
    }
