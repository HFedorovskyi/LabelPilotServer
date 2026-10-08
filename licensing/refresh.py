"""Pick up a renewed licence from the LabelPilot sales service.

A subscription renewal (or extra seats) is issued by the vendor under the SAME
license_id, machine binding and key_version, so the data key does not change.
When the server is online it asks the sales service once a day (and when an
administrator presses "Check for licence update") for the current token of its
licence and installs it if it is genuinely newer. Offline sites keep importing
the .lpl file by hand; nothing here is required for production.

Sends only license_id and machine_id. Disable with LICENSE_REFRESH=0.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import threading
import urllib.request
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("licensing")

_DEFAULT_URL = "https://umvxtfwosbecbzthtjyh.supabase.co/functions/v1/refresh-license"
_lock = threading.Lock()
# The last check (the daily one or the admin's button), for «Лицензия»: kept in memory, so
# after a restart the page shows nothing until the next check.
_last: Optional[dict] = None

UPDATED = "updated"          # a newer token was installed
CURRENT = "current"          # the installed licence is the newest one
NOT_FOUND = "not_found"      # the vendor has no active licence for this id + machine
REJECTED = "rejected"        # the vendor answered with a token we must not install
UNAVAILABLE = "unavailable"  # offline / service error — try again later
DISABLED = "disabled"        # LICENSE_REFRESH=0
NO_LICENSE = "no_license"    # nothing installed (first activation is manual)


@dataclass(frozen=True)
class RefreshResult:
    status: str
    detail: str = ""


def _enabled() -> bool:
    flag = os.getenv("LICENSE_REFRESH", "1").strip().lower()
    return flag not in ("0", "false", "no", "off") and bool(_url())


def _url() -> str:
    return (os.getenv("LICENSE_REFRESH_URL") or _DEFAULT_URL).strip()


def install_license_token(raw: str):
    """Verify a vendor-signed token and atomically replace license.lpl with it."""
    from . import clock
    from .core import _license_path, _verify_and_parse

    lic = _verify_and_parse(raw)  # raises on a bad signature / payload
    path = _license_path()
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(raw, encoding="utf-8")
    os.replace(temporary, path)
    clock.reset_cache()
    return lic


def _fetch_token(license_id: str, machine: str, timeout: float) -> tuple:
    body = json.dumps({"license_id": license_id, "machine_id": machine}).encode("utf-8")
    try:
        from django.conf import settings
        version = str(getattr(settings, "VERSION", "") or "unknown")
    except Exception:
        version = "unknown"
    request = urllib.request.Request(
        _url(), data=body, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": f"LabelPilotServer/{version}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read(256 * 1024).decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("refresh response must be an object")
    token = data.get("token")
    return str(data.get("status") or ""), token if isinstance(token, str) else None


def last_refresh() -> Optional[dict]:
    return dict(_last) if _last else None


def refresh_license(timeout: float = 10.0) -> RefreshResult:
    """Ask the sales service for this licence's current token. Never raises."""
    global _last
    result = _refresh_license(timeout)
    _last = {
        "status": result.status,
        "detail": result.detail,
        "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return result


def _refresh_license(timeout: float) -> RefreshResult:
    if not _enabled():
        return RefreshResult(DISABLED)
    from .core import _verify_and_parse, license_state, machine_id

    with _lock:
        state = license_state()
        current = state.license
        if current is None or not state.machine_ok:
            return RefreshResult(NO_LICENSE)
        try:
            status, token = _fetch_token(current.license_id, machine_id(), timeout)
        except Exception as exc:
            logger.info("licence refresh unavailable: %s", exc)
            return RefreshResult(UNAVAILABLE, str(exc)[:200])
        if status != "ok" or not token:
            return RefreshResult(NOT_FOUND)
        token = token.strip()
        if token == current.token:
            return RefreshResult(CURRENT)
        try:
            candidate = _verify_and_parse(token)
        except Exception:
            logger.warning("licence refresh: the sales service returned a token that does not verify")
            return RefreshResult(REJECTED, "signature")
        if (candidate.license_id, candidate.machine_id, candidate.key_version) != (
            current.license_id, current.machine_id, current.key_version,
        ):
            # Another licence, machine or data key is a manual decision (import).
            return RefreshResult(REJECTED, "identity")
        if (candidate.issued or "") < (current.issued or ""):
            return RefreshResult(CURRENT)  # never roll back to an older issue
        try:
            install_license_token(token)
        except Exception as exc:
            logger.error("licence refresh: could not install the renewed licence: %s", exc)
            return RefreshResult(UNAVAILABLE, str(exc)[:200])
        logger.info(
            "licence %s renewed: expires=%s max_stations=%s",
            candidate.license_id, candidate.expires, candidate.max_stations,
        )
        try:
            from .telemetry import report_license_activated
            report_license_activated(f"refresh:{candidate.license_id}")
        except Exception:
            pass
        return RefreshResult(UPDATED, candidate.expires or "lifetime")


def refresh_quietly() -> Optional[RefreshResult]:
    try:
        return refresh_license()
    except Exception:
        return None
