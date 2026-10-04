"""Commercial license enforcement through independent native and Python checks."""
from __future__ import annotations

import logging
from typing import Optional, Tuple

logger = logging.getLogger("licensing")


class CommercialLicenseDenied(PermissionError):
    """Raised when a commercial export/action is blocked. Callers map this to HTTP 403."""


def _strict_mode() -> bool:
    try:
        from django.conf import settings

        # DEBUG=False is itself a production boundary. LICENSE_REQUIRED can force
        # the same checks in a debug commissioning environment, but it cannot disable them.
        return bool(getattr(settings, "LICENSE_REQUIRED", False)) or not bool(
            getattr(settings, "DEBUG", False)
        )
    except Exception:
        return False


def _fresh_signature_ok(raw: str) -> bool:
    """Independent re-verification that does not trust the license-state cache."""
    try:
        from .core import _verify_and_parse

        _verify_and_parse(raw)
        return True
    except Exception:
        return False


def _read_license_file() -> Optional[str]:
    try:
        from .core import _license_path

        path = _license_path()
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


def _native_reason(reason: str) -> str:
    if reason in {"missing", "license_missing"}:
        return "missing"
    if reason in {"bad_signature", "license_signature", "license_format"}:
        return "bad_signature"
    if reason in {"wrong_machine", "expired"}:
        return reason
    if reason in {
        "manifest_missing",
        "manifest_signature",
        "manifest_contract",
        "manifest_path",
        "integrity_hash",
        "unsigned_code",
    }:
        return "integrity"
    return "native_guard"

def commercial_license_ok() -> Tuple[bool, str]:
    """Return ``(ok, reason_code)`` only when all available checks agree.

    Production requires the native verifier, its signed build manifest, and the
    independent Python verifier. Source-tree development can fall back to Python
    when no release guard/manifest has been staged.
    """
    strict = _strict_mode()

    try:
        from .native_guard import verify_license_native

        native = verify_license_native()
        if native.available and not native.ok:
            return False, _native_reason(native.reason)
        if not native.available and strict:
            return False, "native_guard"
    except Exception:
        logger.exception("native license guard integration failed")
        if strict:
            return False, "native_guard"

    try:
        from .integrity import integrity_ok

        if not integrity_ok():
            return False, "integrity"
    except Exception:
        logger.exception("signed integrity verification failed")
        if strict:
            return False, "integrity"

    raw = _read_license_file()
    if not raw:
        return False, "missing"

    if not _fresh_signature_ok(raw):
        return False, "bad_signature"

    from .core import license_state

    state = license_state()
    if not state.present or not state.signature_valid:
        return False, "bad_signature"
    if not state.machine_ok:
        return False, "wrong_machine"
    if state.past_grace:
        # In the grace period exports keep working; the UI shows the deadline.
        return False, "expired"

    from .core import load_license

    if load_license() is None:
        return False, "wrong_machine"

    return True, "ok"


def assert_export_allowed() -> None:
    """Gate every real-data export, independent of the boot warning mode."""
    ok, reason = commercial_license_ok()
    if ok:
        return
    logger.warning("commercial export denied: %s", reason)
    raise CommercialLicenseDenied(reason)


def assert_encrypt_allowed() -> None:
    """Gate creation of commercial encrypted blobs in production-strict mode."""
    if not _strict_mode():
        return
    ok, reason = commercial_license_ok()
    if not ok:
        logger.warning("encrypt denied (strict): %s", reason)
        raise CommercialLicenseDenied(reason)


def require_export_or_http() -> None:
    """DRF-friendly wrapper around the commercial export gate."""
    try:
        assert_export_allowed()
    except CommercialLicenseDenied as exc:
        try:
            from licensing.telemetry import report_export_denied

            report_export_denied(reason=str(exc) or "missing", detail="export")
        except Exception:
            pass
        from rest_framework.exceptions import PermissionDenied

        try:
            from api.i18n import tr

            message = tr("license.exportDenied")
        except Exception:
            message = "A valid license is required to export data to stations."
        raise PermissionDenied(message) from exc
