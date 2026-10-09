"""Vendor-signed seat list: the workstations that hold a seat of this licence.

A licence whose token carries the ``seat-list`` feature makes stations (client
2.0.6+) accept data only when it comes with a list signed by the vendor that
names their own hardware fingerprint. This server cannot sign lists: the sales
service does, keeping each list within the licence's seats and the release
allowance. A modified server can therefore not add stations beyond the seats
sold — the stations themselves refuse the data.

The list (``license-seats.lst`` next to ``license.lpl``):
    <b64url(canonical payload JSON)>.<b64url(ed25519 signature)>
    payload = {expires, issued, kind, license_id, machine_id, max_stations, stations}

It expires after 90 days. An online server asks the sales service for a fresh
list once a day and a few seconds after every seat change, proving itself with a
random secret it generated on its first request (``license-seats.link``). An
offline site downloads a request file here, has it signed in the customer
cabinet and imports the list it gets back.

Nothing here stops production: without a valid list the stations keep printing
with the data they have; only new data does not reach them.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import secrets
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = logging.getLogger("licensing")

SEAT_LIST_FEATURE = "seat-list"
SEAT_LIST_KIND = "labelpilot-seats-v1"
SEAT_REQUEST_KIND = "labelpilot-seat-request-v1"
RENEWAL_NOTICE_DAYS = 30
SYNC_DELAY_SECONDS = 5.0

_FILENAME = "license-seats.lst"
_LINK_FILENAME = "license-seats.link"
_TOKEN_LIMIT = 4 * 1024 * 1024
_MAX_STATIONS = 100_000
_FIELDS = {"expires", "issued", "kind", "license_id", "machine_id", "max_stations", "stations"}
_FINGERPRINT_RE = re.compile(r"[0-9a-f]{32}\Z")
_LICENSE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,79}\Z")
_ISSUED_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_SECRET_RE = re.compile(r"[0-9a-f]{64}\Z")
_DEFAULT_URL = "https://umvxtfwosbecbzthtjyh.supabase.co/functions/v1/seat-list"

UPDATED = "updated"            # a fresh list was installed
REJECTED = "rejected"          # the vendor refused the change (code in detail)
NOT_FOUND = "not_found"        # the vendor has no active licence for this id + machine
UNAVAILABLE = "unavailable"    # offline / service error — try again later
DISABLED = "disabled"          # SEAT_LIST_SYNC=0 (offline site: use request/import)
NOT_REQUIRED = "not_required"  # the licence does not use seat lists

_lock = threading.Lock()          # one sync at a time
_timer_lock = threading.Lock()
_cache_lock = threading.Lock()
_cache: Optional[tuple] = None  # ((path, mtime_ns, size), SeatList | None)
_timer: Optional[threading.Timer] = None
_last_sync: Optional[dict] = None


@dataclass(frozen=True)
class SeatList:
    license_id: str
    machine_id: str
    max_stations: Optional[int]
    stations: tuple
    issued: str
    expires: datetime.date
    token: str

    def lists(self, fingerprint) -> bool:
        return isinstance(fingerprint, str) and fingerprint in self.stations

    def is_expired(self, today: datetime.date) -> bool:
        return today > self.expires


def _b64url_decode(value: str) -> bytes:
    from .core import _b64url_decode as decode

    return decode(value)


def _object_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate seat list field: {key}")
        result[key] = value
    return result


def verify_seat_list(raw: str, public_key_hex: Optional[str] = None) -> SeatList:
    """A seat list token verified against the vendor key and the exact contract."""
    from .core import LICENSE_PUBLIC_KEY_HEX

    token = (raw or "").strip()
    if not token or len(token.encode("utf-8")) > _TOKEN_LIMIT:
        raise ValueError("seat list has an invalid size")
    parts = token.split(".")
    if len(parts) != 2 or not all(parts):
        raise ValueError("seat list is malformed")
    payload_bytes = _b64url_decode(parts[0])
    signature = _b64url_decode(parts[1])
    if len(signature) != 64:
        raise ValueError("seat list signature has an invalid size")
    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex or LICENSE_PUBLIC_KEY_HEX))
    key.verify(signature, payload_bytes)

    payload = json.loads(payload_bytes.decode("utf-8"), object_pairs_hook=_object_without_duplicates)
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        raise ValueError("seat list fields do not match the contract")
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if canonical != payload_bytes:
        raise ValueError("seat list is not canonical JSON")
    if payload["kind"] != SEAT_LIST_KIND:
        raise ValueError("not a seat list")
    license_id = payload["license_id"]
    if not isinstance(license_id, str) or not _LICENSE_ID_RE.fullmatch(license_id):
        raise ValueError("seat list licence id is invalid")
    machine = payload["machine_id"]
    if not isinstance(machine, str) or not _FINGERPRINT_RE.fullmatch(machine):
        raise ValueError("seat list machine id is invalid")
    issued = payload["issued"]
    if not isinstance(issued, str) or not _ISSUED_RE.fullmatch(issued):
        raise ValueError("seat list issue time is invalid")
    datetime.datetime.strptime(issued, "%Y-%m-%dT%H:%M:%SZ")
    expires_text = payload["expires"]
    if not isinstance(expires_text, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expires_text):
        raise ValueError("seat list expiry is invalid")
    expires = datetime.date.fromisoformat(expires_text)
    maximum = payload["max_stations"]
    if maximum is not None and (
        isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= _MAX_STATIONS
    ):
        raise ValueError("seat list seat count is invalid")
    stations = payload["stations"]
    if (
        not isinstance(stations, list) or len(stations) > _MAX_STATIONS
        or any(not isinstance(item, str) or not _FINGERPRINT_RE.fullmatch(item) for item in stations)
        or stations != sorted(set(stations))
    ):
        raise ValueError("seat list stations are not sorted unique fingerprints")
    if maximum is not None and len(stations) > maximum:
        raise ValueError("seat list holds more stations than seats")
    return SeatList(
        license_id=license_id, machine_id=machine, max_stations=maximum,
        stations=tuple(stations), issued=issued, expires=expires, token=token,
    )


def _list_path() -> Path:
    override = os.getenv("LABELPILOT_SEAT_LIST_PATH", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / _FILENAME


def _link_path() -> Path:
    override = os.getenv("LABELPILOT_SEAT_LIST_LINK_PATH", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / _LINK_FILENAME


def _write_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def reset_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def stored() -> Optional[SeatList]:
    """The list file as installed, verified; None when missing or invalid."""
    global _cache
    path = _list_path()
    try:
        stat = path.stat()
    except OSError:
        return None
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    with _cache_lock:
        if _cache is not None and _cache[0] == key:
            return _cache[1]
    try:
        value = verify_seat_list(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("seat list file is not a valid vendor-signed list")
        value = None
    with _cache_lock:
        _cache = (key, value)
    return value


def _licence():
    """The installed licence when it is valid for this machine, else None."""
    from .core import license_state

    state = license_state()
    if not (state.valid_for_key and state.machine_ok) or state.license is None:
        return None
    return state.license


def _today() -> datetime.date:
    from .core import license_state

    return license_state().today or datetime.date.today()


def required() -> bool:
    lic = _licence()
    return bool(lic and SEAT_LIST_FEATURE in (lic.features or []))


def current() -> Optional[SeatList]:
    """The installed list when it belongs to the installed licence (expired or not)."""
    lic = _licence()
    value = stored()
    if lic is None or value is None:
        return None
    if (value.license_id, value.machine_id) != (lic.license_id, lic.machine_id):
        return None
    return value


def valid_list() -> Optional[SeatList]:
    value = current()
    return value if value is not None and not value.is_expired(_today()) else None


def listed_fingerprints() -> Optional[frozenset]:
    """Fingerprints that may receive data; None when the licence uses no seat list."""
    if not required():
        return None
    value = valid_list()
    return frozenset(value.stations) if value is not None else frozenset()


def station_listed(station, listed: Optional[frozenset] = None) -> bool:
    if listed is None:
        listed = listed_fingerprints()
        if listed is None:
            return True
    fingerprint = getattr(station, "station_fingerprint", "") or ""
    return bool(fingerprint) and fingerprint in listed


def push_token() -> Optional[str]:
    """The list every LPI2 payload carries for the stations to check (when required)."""
    if not required():
        return None
    value = current()
    return value.token if value is not None else None


def wanted_stations() -> list:
    """Fingerprints of the stations holding a seat within the licence's cap."""
    from .seats import SEAT_ACTIVE, _stations, seated_ids

    seated = seated_ids()
    stations = _stations().filter(seat_state=SEAT_ACTIVE).exclude(station_fingerprint="")
    if seated is not None:
        stations = stations.filter(pk__in=seated)
    fingerprints = {fp for fp in stations.values_list("station_fingerprint", flat=True) if _FINGERPRINT_RE.fullmatch(fp or "")}
    return sorted(fingerprints)


def install(raw: str) -> SeatList:
    """Verify a list and install it atomically. It must belong to the installed
    licence and must not be older than the list already installed."""
    value = verify_seat_list(raw)
    lic = _licence()
    if lic is None:
        raise ValueError("no valid licence is installed on this server")
    if (value.license_id, value.machine_id) != (lic.license_id, lic.machine_id):
        raise ValueError("the seat list belongs to another licence or server")
    existing = current()
    if existing is not None and value.issued < existing.issued:
        raise ValueError("the seat list is older than the installed one")
    _write_atomic(_list_path(), value.token)
    reset_cache()
    return value


def request_document() -> dict:
    """The file an offline site has signed in the customer cabinet."""
    lic = _licence()
    if lic is None:
        raise ValueError("no valid licence is installed on this server")
    return {
        "kind": SEAT_REQUEST_KIND,
        "license_id": lic.license_id,
        "machine_id": lic.machine_id,
        "stations": wanted_stations(),
        "created": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _link_secret() -> str:
    """This installation's proof towards the sales service, created on first use."""
    path = _link_path()
    try:
        text = path.read_text(encoding="utf-8").strip().lower()
        if _SECRET_RE.fullmatch(text):
            return text
    except OSError:
        pass
    secret = secrets.token_hex(32)
    _write_atomic(path, secret)
    return secret


def _linked() -> bool:
    try:
        return bool(_SECRET_RE.fullmatch(_link_path().read_text(encoding="utf-8").strip().lower()))
    except OSError:
        return False


def sync_enabled() -> bool:
    flag = os.getenv("SEAT_LIST_SYNC", os.getenv("LICENSE_REFRESH", "1")).strip().lower()
    return flag not in ("0", "false", "no", "off") and bool(_url())


def _url() -> str:
    return (os.getenv("SEAT_LIST_URL") or _DEFAULT_URL).strip()


@dataclass(frozen=True)
class SyncResult:
    status: str
    detail: str = ""


def _record(result: SyncResult) -> SyncResult:
    global _last_sync
    _last_sync = {
        "status": result.status,
        "detail": result.detail,
        "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return result


def _post(body: dict, timeout: float) -> dict:
    try:
        from django.conf import settings
        version = str(getattr(settings, "VERSION", "") or "unknown")
    except Exception:
        version = "unknown"
    request = urllib.request.Request(
        _url(), data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": f"LabelPilotServer/{version}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read(_TOKEN_LIMIT + 64 * 1024).decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("seat list response must be an object")
    return data


def sync(timeout: float = 10.0) -> SyncResult:
    """Ask the sales service to sign the list of the stations holding a seat. Never raises."""
    if not required():
        return SyncResult(NOT_REQUIRED)
    if not sync_enabled():
        return SyncResult(DISABLED)
    with _lock:
        lic = _licence()
        if lic is None:
            return SyncResult(NOT_REQUIRED)
        try:
            body = {
                "license_id": lic.license_id,
                "machine_id": lic.machine_id,
                "stations": wanted_stations(),
                "sync_secret": _link_secret(),
            }
            data = _post(body, timeout)
        except Exception as exc:
            logger.info("seat list sync unavailable: %s", exc)
            return _record(SyncResult(UNAVAILABLE, str(exc)[:200]))
        status = str(data.get("status") or "")
        if status == "rejected":
            code = str(data.get("code") or "")[:64]
            logger.warning("seat list sync rejected by the vendor: %s", code)
            return _record(SyncResult(REJECTED, code))
        token = data.get("token")
        if status != "ok" or not isinstance(token, str):
            return _record(SyncResult(NOT_FOUND))
        try:
            value = install(token)
        except Exception as exc:
            logger.warning("seat list sync: the vendor list was not installed: %s", exc)
            return _record(SyncResult(REJECTED, "install"))
        logger.info("seat list renewed: %d stations, expires %s", len(value.stations), value.expires)
        return _record(SyncResult(UPDATED, value.expires.isoformat()))


def sync_quietly() -> Optional[SyncResult]:
    try:
        return sync()
    except Exception:
        return None


def schedule_sync(delay: float = SYNC_DELAY_SECONDS) -> None:
    """Debounced sync after a seat change (several changes in a row cost one request)."""
    global _timer
    try:
        if not required() or not sync_enabled():
            return
    except Exception:
        return
    with _timer_lock:
        if _timer is not None:
            _timer.cancel()
        _timer = threading.Timer(delay, sync_quietly)
        _timer.daemon = True
        _timer.start()


def status() -> dict:
    """Facts for the licence screen."""
    is_required = required()
    value = current()
    today = _today()
    wanted = wanted_stations() if is_required else []
    listed = set(value.stations) if value is not None else set()
    days_left = (value.expires - today).days if value is not None else None
    return {
        "required": is_required,
        "present": value is not None,
        "issued": value.issued if value else None,
        "expires": value.expires.isoformat() if value else None,
        "expired": bool(value is not None and value.is_expired(today)),
        "days_left": max(0, days_left) if days_left is not None else None,
        "renewal_due": bool(value is not None and days_left is not None and days_left <= RENEWAL_NOTICE_DAYS),
        "stations": len(listed),
        "limit": value.max_stations if value else None,
        "missing": len([fp for fp in wanted if fp not in listed]),
        "extra": len(listed - set(wanted)),
        "in_sync": bool(value is not None and listed == set(wanted)),
        "linked": _linked(),
        "sync_enabled": sync_enabled(),
        "last_sync": dict(_last_sync) if _last_sync else None,
    }
