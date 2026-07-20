"""Optional install phone-home to the LabelPilot Sales service.

When LICENSE_TELEMETRY_URL is set (full URL to report-install Edge Function), the
server POSTs a minimal status once per day (machine_id + license flags + version).
Never raises to callers. Skips silently if offline, disabled, or misconfigured.

Disable on air-gapped sites:
  LICENSE_TELEMETRY_URL=   (empty / unset)
  or LICENSE_TELEMETRY=0
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger("licensing")

_DEFAULT_URL = "https://umvxtfwosbecbzthtjyh.supabase.co/functions/v1/report-install"
_MIN_INTERVAL_SEC = 20 * 60 * 60  # ~20 hours → effectively once/day


def _marker_path() -> Path:
    # backend/ next to .env / license.lpl
    return Path(__file__).resolve().parent.parent / ".telemetry_last"


def _should_send() -> bool:
    flag = os.getenv("LICENSE_TELEMETRY", "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    path = _marker_path()
    try:
        if path.is_file():
            age = time.time() - path.stat().st_mtime
            if age < _MIN_INTERVAL_SEC:
                return False
    except OSError:
        pass
    return True


def _mark_sent() -> None:
    try:
        _marker_path().write_text(str(int(time.time())), encoding="ascii")
    except OSError:
        pass


def build_payload() -> dict:
    from django.conf import settings
    from licensing.core import license_state, machine_id
    from licensing.enforcement import commercial_license_ok

    st = license_state()
    ok, _reason = commercial_license_ok()
    lic = st.license
    return {
        "machine_id": machine_id(),
        "licensed": bool(ok),
        "license_id": lic.license_id if lic else None,
        "signature_valid": bool(st.signature_valid),
        "machine_ok": bool(st.machine_ok),
        "expired": bool(st.expired),
        "commercial_ok": bool(ok),
        "app_version": str(getattr(settings, "VERSION", "") or ""),
    }


def send_install_report(timeout: float = 5.0) -> bool:
    """POST one report. Returns True on HTTP 2xx. Never raises."""
    url = (os.getenv("LICENSE_TELEMETRY_URL") or _DEFAULT_URL).strip()
    if not url:
        return False
    if not _should_send():
        return False
    try:
        payload = build_payload()
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": f"LabelPilotServer/{payload.get('app_version') or 'unknown'}",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ok = 200 <= getattr(resp, "status", 200) < 300
        if ok:
            _mark_sent()
        return ok
    except Exception as e:
        logger.debug("install telemetry skipped/failed: %s", e)
        return False


def schedule_install_report(delay_sec: float = 8.0) -> None:
    """Fire-and-forget after boot (does not block Django ready())."""
    def _run() -> None:
        try:
            time.sleep(max(0.0, delay_sec))
            send_install_report()
        except Exception:
            pass

    try:
        t = threading.Thread(target=_run, name="lp-license-telemetry", daemon=True)
        t.start()
    except Exception:
        pass
