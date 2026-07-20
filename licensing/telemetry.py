"""Optional license telemetry to the LabelPilot Sales service.

Reports (when internet is available):
  - boot / heartbeat (status)
  - license_activated (after .lpl install)
  - export_denied / encrypt_denied / unlicensed_use (commercial attempts without license)

Never raises to callers. Skips silently if offline, disabled, or misconfigured.
Does NOT send catalog, labels, production or personal customer data — only license
status, machine_id, version, and short reason/detail codes.

Disable on air-gapped sites:
  LICENSE_TELEMETRY=0
  or LICENSE_TELEMETRY_URL=
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger("licensing")

_DEFAULT_URL = "https://umvxtfwosbecbzthtjyh.supabase.co/functions/v1/report-install"

# Min seconds between identical event+reason for the same machine (spam control).
_EVENT_COOLDOWN = {
    "heartbeat": 20 * 60 * 60,
    "boot": 6 * 60 * 60,
    "license_activated": 60,          # allow a few retries
    "export_denied": 5 * 60,          # full log, but not every click
    "encrypt_denied": 5 * 60,
    "unlicensed_use": 5 * 60,
}


def _enabled() -> bool:
    flag = os.getenv("LICENSE_TELEMETRY", "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    url = (os.getenv("LICENSE_TELEMETRY_URL") or _DEFAULT_URL).strip()
    return bool(url)


def _url() -> str:
    return (os.getenv("LICENSE_TELEMETRY_URL") or _DEFAULT_URL).strip()


def _state_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _cooldown_path(event: str, reason: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in f"{event}_{reason}")[:80]
    return _state_dir() / f".telemetry_{safe}"


def _cooldown_ok(event: str, reason: str, force: bool) -> bool:
    if force:
        return True
    path = _cooldown_path(event, reason)
    min_age = _EVENT_COOLDOWN.get(event, 10 * 60)
    try:
        if path.is_file():
            if time.time() - path.stat().st_mtime < min_age:
                return False
    except OSError:
        pass
    return True


def _mark_cooldown(event: str, reason: str) -> None:
    try:
        _cooldown_path(event, reason).write_text(str(int(time.time())), encoding="ascii")
    except OSError:
        pass


def build_status_fields() -> dict:
    from django.conf import settings
    from licensing.core import license_state, machine_id
    from licensing.enforcement import commercial_license_ok

    st = license_state()
    ok, reason = commercial_license_ok()
    lic = st.license
    return {
        "machine_id": machine_id(),
        "licensed": bool(ok),
        "license_id": lic.license_id if lic else None,
        "signature_valid": bool(st.signature_valid),
        "machine_ok": bool(st.machine_ok),
        "expired": bool(st.expired),
        "commercial_ok": bool(ok),
        "reason": reason if not ok else None,
        "app_version": str(getattr(settings, "VERSION", "") or ""),
    }


def send_event(
    event: str,
    *,
    reason: Optional[str] = None,
    detail: Optional[str] = None,
    force: bool = False,
    timeout: float = 5.0,
) -> bool:
    """POST one license event. Returns True on HTTP 2xx. Never raises."""
    if not _enabled():
        return False
    event = (event or "heartbeat").strip().lower()
    reason_key = (reason or "").strip() or "none"
    if not _cooldown_ok(event, reason_key, force):
        return False
    try:
        payload = build_status_fields()
        payload["event"] = event
        if reason:
            payload["reason"] = str(reason)[:120]
        elif payload.get("reason") is None and event in ("export_denied", "encrypt_denied", "unlicensed_use"):
            payload["reason"] = "missing"
        if detail:
            payload["detail"] = str(detail)[:240]
        # For denial events, always mark unlicensed in payload for filtering.
        if event in ("export_denied", "encrypt_denied", "unlicensed_use"):
            payload["licensed"] = False
            payload["commercial_ok"] = False

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _url(),
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
            _mark_cooldown(event, reason_key)
        return ok
    except Exception as e:
        logger.debug("license telemetry failed (%s): %s", event, e)
        return False


def report_event_async(
    event: str,
    *,
    reason: Optional[str] = None,
    detail: Optional[str] = None,
    force: bool = False,
) -> None:
    """Fire-and-forget; never blocks request handlers."""
    def _run() -> None:
        try:
            send_event(event, reason=reason, detail=detail, force=force)
        except Exception:
            pass

    try:
        threading.Thread(target=_run, name=f"lp-tel-{event}", daemon=True).start()
    except Exception:
        pass


def send_install_report(timeout: float = 5.0) -> bool:
    """Backward-compatible boot/heartbeat report."""
    return send_event("heartbeat", timeout=timeout)


def schedule_install_report(delay_sec: float = 8.0) -> None:
    """Fire-and-forget after boot (does not block Django ready())."""
    def _run() -> None:
        try:
            time.sleep(max(0.0, delay_sec))
            # boot once, then heartbeat uses cooldown for later process restarts same day
            send_event("boot", force=False)
        except Exception:
            pass

    try:
        threading.Thread(target=_run, name="lp-license-telemetry", daemon=True).start()
    except Exception:
        pass


def report_license_activated(license_id: Optional[str] = None) -> None:
    report_event_async("license_activated", detail=license_id or "", force=True)


def report_export_denied(reason: str = "missing", detail: str = "export") -> None:
    report_event_async("export_denied", reason=reason, detail=detail)


def report_encrypt_denied(reason: str = "missing") -> None:
    report_event_async("encrypt_denied", reason=reason, detail="encrypt_data")


def report_unlicensed_use(detail: str = "") -> None:
    report_event_async("unlicensed_use", reason="missing", detail=detail)
