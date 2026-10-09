"""Small process boundary around the native license/integrity verifier."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("licensing")

CACHE_SECONDS = 5.0
PROCESS_TIMEOUT_SECONDS = 8.0
_cache: Optional[Tuple[float, tuple, "NativeGuardResult"]] = None


@dataclass(frozen=True)
class NativeGuardResult:
    available: bool
    ok: bool
    reason: str
    detail: str = ""


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


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


def _candidate_executables() -> tuple[Path, ...]:
    root = _backend_root()
    configured = os.getenv("LABELPILOT_LICENSE_GUARD", "").strip()
    candidates = []
    if configured:
        candidates.append(Path(configured))
    executable = "labelpilot-license-guard.exe" if os.name == "nt" else "labelpilot-license-guard"
    candidates.extend(
        (
            root.parent.parent / "tools" / executable,
            root.parent / "tools" / executable,
            root.parent / "native" / "license-guard" / "target" / "release" / executable,
            root.parent / "native" / "license-guard" / "target" / "debug" / executable,
        )
    )
    return tuple(candidates)


def guard_executable() -> Optional[Path]:
    for candidate in _candidate_executables():
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _file_state(path: Path) -> tuple:
    try:
        stat = path.stat()
        return str(path), stat.st_mtime_ns, stat.st_size
    except OSError:
        return str(path), None, None


def _cache_key(executable: Optional[Path], manifest: Path, license_path: Path) -> tuple:
    return tuple(_file_state(path) for path in (executable, manifest, license_path) if path)


def _decode_result(completed: subprocess.CompletedProcess[str]) -> NativeGuardResult:
    raw = (completed.stdout or "").strip()
    payload = None
    if raw:
        try:
            payload = json.loads(raw.splitlines()[-1])
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = None
    if isinstance(payload, dict):
        ok = bool(payload.get("ok")) and completed.returncode == 0
        reason = str(payload.get("reason") or ("ok" if ok else "native_guard"))
        detail = str(payload.get("detail") or "")
        return NativeGuardResult(True, ok, reason, detail)
    detail = (completed.stderr or raw or f"exit {completed.returncode}").strip()[:500]
    return NativeGuardResult(True, False, "native_guard", detail)


def _guard_is_signed(executable: Path) -> bool:
    """The guard binary must be the one the vendor signed into the release manifest:
    a stub that always prints {"ok": true} is refused before it is ever run."""
    from .integrity import IntegrityError, file_digest, signed_guard_record

    try:
        record = signed_guard_record()
    except IntegrityError as exc:
        logger.error("license guard cannot be authenticated: %s", exc)
        return False
    if record is None:
        # Source tree without a release manifest: production must have one.
        return not _strict_mode()
    try:
        size, digest = file_digest(executable)
    except Exception as exc:
        logger.error("license guard is unreadable: %s", exc)
        return False
    return size == record["size"] and digest == record["sha256"]


def _trusted_date() -> str:
    try:
        from .core import license_state

        today = license_state().today
        return today.isoformat() if today else ""
    except Exception:
        return ""


def verify_license_native(force_reload: bool = False) -> NativeGuardResult:
    """Verify signed build + installed license in the native process.

    Development trees without a release manifest/guard report ``available=False``;
    strict production callers treat that as a denial.
    """
    global _cache
    root = _backend_root()
    executable = guard_executable()
    manifest = root / "licensing" / "_fingerprint.lpf"
    license_path = root / "license.lpl"
    not_before = _trusted_date()
    key = _cache_key(executable, manifest, license_path) + (not_before,)
    now = time.monotonic()
    if (
        not force_reload
        and _cache is not None
        and now - _cache[0] < CACHE_SECONDS
        and _cache[1] == key
    ):
        return _cache[2]

    if executable is None or not manifest.is_file():
        missing = []
        if executable is None:
            missing.append("executable")
        if not manifest.is_file():
            missing.append("manifest")
        result = NativeGuardResult(False, not _strict_mode(), "native_guard_missing", ",".join(missing))
        _cache = (now, key, result)
        return result

    if not _guard_is_signed(executable):
        result = NativeGuardResult(True, False, "native_guard", "guard binary is not the signed release")
        _cache = (now, key, result)
        return result

    command = [
        str(executable),
        "verify-license",
        "--root",
        str(root),
        "--manifest",
        str(manifest),
        "--license",
        str(license_path),
        "--json",
    ]
    if not_before:
        # The licence clock mark (licensing.clock): turning the OS clock back
        # must not make the native verifier accept an expired licence again.
        command += ["--not-before", not_before]
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROCESS_TIMEOUT_SECONDS,
            check=False,
            creationflags=creation_flags,
        )
        result = _decode_result(completed)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("native license guard failed to run: %s", exc)
        result = NativeGuardResult(True, False, "native_guard", str(exc)[:500])
    _cache = (now, key, result)
    return result


def native_guard_status() -> dict:
    result = verify_license_native()
    return {
        "available": result.available,
        "ok": result.ok,
        "reason": result.reason,
        "detail": result.detail,
    }
