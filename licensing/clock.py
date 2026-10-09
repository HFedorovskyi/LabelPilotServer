"""Trusted date for licence expiry: a guard against turning the server clock back.

A subscription licence is judged against the latest moment this installation is
known to have reached, not the bare OS clock:

  * a high-water mark persisted next to the licence (HMAC-signed with SECRET_KEY,
    so it cannot be edited back to an earlier date);
  * when that file is missing, the newest server-side timestamp in the database
    (labels and logs received, server events, seat events) — deleting the file
    therefore does not reset the guard;
  * the signed ``issued`` date of the installed licence (the vendor proves that
    real time has reached it).

Turning the clock back more than a day is reported as ``rollback`` and expiry is
evaluated at the mark. A vendor re-issue (a licence with a later ``issued`` date)
re-bases the mark, which also clears a mark pushed into the future by a clock
that was once set wrong. Nothing here stops production: it only decides which
date the commercial gates see.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("licensing")

GRACE_DAYS = 14
ROLLBACK_TOLERANCE = datetime.timedelta(days=1)
_WRITE_INTERVAL = datetime.timedelta(minutes=10)
_READING_TTL_SECONDS = 60.0
_MARK_FILENAME = "license-clock.json"

_lock = threading.Lock()
_cached: Optional[tuple] = None  # (monotonic, issued, ClockReading)
_last_written: Optional[datetime.datetime] = None


@dataclass(frozen=True)
class ClockReading:
    now: datetime.datetime        # the OS clock (UTC)
    mark: datetime.datetime       # latest moment this installation is known to have reached
    rollback: bool                # the OS clock is more than a day behind the mark

    @property
    def effective(self) -> datetime.datetime:
        return self.mark if self.rollback else self.now

    @property
    def today(self) -> datetime.date:
        return self.effective.date()


def _utcnow() -> datetime.datetime:
    try:
        from django.utils import timezone
        return timezone.now().astimezone(datetime.timezone.utc)
    except Exception:
        return datetime.datetime.now(datetime.timezone.utc)


def _mark_path() -> Path:
    override = os.getenv("LABELPILOT_LICENSE_CLOCK_PATH", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / _MARK_FILENAME


def _signing_key() -> bytes:
    try:
        from django.conf import settings
        secret = str(getattr(settings, "SECRET_KEY", "") or "")
    except Exception:
        secret = ""
    return hashlib.sha256(b"labelpilot-license-clock|v1|" + secret.encode("utf-8")).digest()


def _signature(mark: str, issued: str) -> str:
    message = f"{mark}|{issued}".encode("utf-8")
    return hmac.new(_signing_key(), message, hashlib.sha256).hexdigest()


def _parse_moment(value) -> Optional[datetime.datetime]:
    try:
        moment = datetime.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment.astimezone(datetime.timezone.utc)


def _start_of(day: Optional[str]) -> Optional[datetime.datetime]:
    try:
        date = datetime.date.fromisoformat(str(day))
    except (TypeError, ValueError):
        return None
    return datetime.datetime.combine(date, datetime.time.min, tzinfo=datetime.timezone.utc)


def _read_mark() -> Optional[tuple]:
    """(mark, issued) from a file whose signature verifies, else None."""
    try:
        data = json.loads(_mark_path().read_text(encoding="utf-8"))
        mark, issued, signature = str(data["mark"]), str(data.get("issued") or ""), str(data["sig"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not hmac.compare_digest(signature, _signature(mark, issued)):
        logger.warning("license clock mark has an invalid signature; rebuilding it from the database")
        return None
    moment = _parse_moment(mark)
    return (moment, issued) if moment else None


def _write_mark(mark: datetime.datetime, issued: str) -> None:
    global _last_written
    text = mark.isoformat()
    payload = json.dumps({"mark": text, "issued": issued, "sig": _signature(text, issued)})
    path = _mark_path()
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, path)
        _last_written = mark
    except OSError as exc:
        logger.warning("could not persist the license clock mark: %s", exc)


def _database_mark() -> Optional[datetime.datetime]:
    """Newest server-side timestamp (auto_now_add rows only, never station clocks)."""
    from django.db.models import Max

    sources = (
        ("ProductionLogs.models", "PrintedLabel"),
        ("ProductionLogs.models", "StationLog"),
        ("server_activity.models", "ServerEvent"),
        ("label_stations.models", "SeatEvent"),
    )
    newest = None
    for module_name, model_name in sources:
        try:
            module = __import__(module_name, fromlist=[model_name])
            value = getattr(module, model_name).objects.aggregate(latest=Max("created_at"))["latest"]
        except Exception:
            continue
        if value is not None:
            value = value.astimezone(datetime.timezone.utc)
            newest = value if newest is None or value > newest else newest
    return newest


def read_clock(issued: Optional[str] = None) -> ClockReading:
    """The trusted clock for a licence with the given signed ``issued`` date."""
    global _cached
    issued = issued or ""
    with _lock:
        if _cached is not None and _cached[1] == issued and time.monotonic() - _cached[0] < _READING_TTL_SECONDS:
            return _cached[2]
        reading = _observe(issued)
        _cached = (time.monotonic(), issued, reading)
        return reading


def _observe(issued: str) -> ClockReading:
    now = _utcnow()
    stored = _read_mark()
    issued_start = _start_of(issued)
    if stored is None:
        mark = _database_mark() or now
        changed = True
    else:
        mark, stored_issued = stored
        changed = False
        if issued and issued > stored_issued:
            # The vendor re-issued the licence: earlier anomalies are forgiven.
            mark = now
            changed = True
    if issued_start is not None and issued_start > mark:
        mark = issued_start
        changed = True
    rollback = now < mark - ROLLBACK_TOLERANCE
    if now > mark:
        if _last_written is None or now - _last_written >= _WRITE_INTERVAL:
            changed = True
        mark = now
    if changed:
        _write_mark(mark, issued)
    if rollback:
        logger.warning("server clock %s is behind the licence clock mark %s", now.isoformat(), mark.isoformat())
        try:
            from .telemetry import report_clock_rollback
            report_clock_rollback(f"now={now.date().isoformat()} mark={mark.date().isoformat()}")
        except Exception:
            pass
    return ClockReading(now=now, mark=mark, rollback=rollback)


def reset_cache() -> None:
    """Tests and licence installation: forget the cached reading."""
    global _cached, _last_written
    with _lock:
        _cached = None
        _last_written = None
