"""Commercial license enforcement — multiple independent checks.

Design goals (honest offline DRM, not military-grade):
  1. One deleted `if` in api/views.py must NOT be enough to open all exports.
  2. Signature is re-verified on the commercial path (not only a cached flag).
  3. Integrity fingerprint of critical modules is checked (patching .py without
     updating the fingerprint fails the gate in production).
  4. Demo / pre-license installs still work when DJANGO_DEBUG=1 or LICENSE_REQUIRED=0.

Nothing here stops a determined reverse engineer forever — it raises the cost of
a casual "delete one function" crack.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

logger = logging.getLogger("licensing")


class CommercialLicenseDenied(PermissionError):
    """Raised when a commercial export/action is blocked. Callers map this to HTTP 403."""


def _fresh_signature_ok(raw: str) -> bool:
    """Independent re-verify of the raw token (does not trust the license_state cache)."""
    try:
        from .core import _verify_and_parse
        _verify_and_parse(raw)
        return True
    except Exception:
        return False


def _read_license_file() -> Optional[str]:
    try:
        from .core import _license_path
        p = _license_path()
        if not p.is_file():
            return None
        return p.read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


def commercial_license_ok() -> Tuple[bool, str]:
    """Return (ok, reason_code). All sub-checks must agree.

    reason_code is stable for logs/UI: missing | bad_signature | integrity | wrong_machine | expired | ok
    """
    # 1) Integrity of critical modules (fail closed only when production-strict).
    try:
        from .integrity import integrity_ok
        if not integrity_ok():
            return False, "integrity"
    except Exception:
        # If integrity module itself is missing/broken in a prod build, fail closed when strict.
        from django.conf import settings
        if getattr(settings, "LICENSE_REQUIRED", False) and not getattr(settings, "DEBUG", False):
            return False, "integrity"

    raw = _read_license_file()
    if not raw:
        return False, "missing"

    # 2) Fresh cryptographic verify (ignores cache).
    if not _fresh_signature_ok(raw):
        return False, "bad_signature"

    # 3) Cached state (machine + expiry + present) — must still match.
    from .core import license_state
    st = license_state()
    if not st.present or not st.signature_valid:
        return False, "bad_signature"
    if not st.machine_ok:
        return False, "wrong_machine"
    if st.expired:
        return False, "expired"

    # 4) load_license() path must also accept (wrong machine returns None).
    from .core import load_license
    if load_license() is None:
        return False, "wrong_machine"

    return True, "ok"


def assert_export_allowed() -> None:
    """Hard gate for any real-data export to stations (online sync, .lpi/.lps/.lpj, full_dump).

    Always enforced — independent of LICENSE_REQUIRED. That setting only controls
    crypto fail-closed / integrity strictness / boot warnings.
    """
    ok, reason = commercial_license_ok()
    if ok:
        return
    logger.warning("commercial export denied: %s", reason)
    raise CommercialLicenseDenied(reason)


def assert_encrypt_allowed() -> None:
    """Second gate used from crypto_utils.encrypt_data.

    In production (LICENSE_REQUIRED and not DEBUG) refuse to mint LPI2/legacy
    commercial blobs without a fully valid commercial license. In dev/lenient
    mode this is a no-op so local testing still works without a license.lpl.
    """
    try:
        from django.conf import settings
        strict = bool(getattr(settings, "LICENSE_REQUIRED", False)) and not bool(
            getattr(settings, "DEBUG", False)
        )
    except Exception:
        strict = False
    if not strict:
        return
    ok, reason = commercial_license_ok()
    if not ok:
        logger.warning("encrypt denied (strict): %s", reason)
        raise CommercialLicenseDenied(reason)


def require_export_or_http() -> None:
    """DRF-friendly wrapper: CommercialLicenseDenied -> rest_framework PermissionDenied."""
    try:
        assert_export_allowed()
    except CommercialLicenseDenied as e:
        # Full log of unlicensed commercial export attempts (async, never blocks).
        try:
            from licensing.telemetry import report_export_denied
            report_export_denied(reason=str(e) or "missing", detail="export")
        except Exception:
            pass
        from rest_framework.exceptions import PermissionDenied
        try:
            from api.i18n import tr
            msg = tr("license.exportDenied")
        except Exception:
            msg = "A valid license is required to export data to stations."
        raise PermissionDenied(msg)
