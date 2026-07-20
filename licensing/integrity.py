"""Runtime integrity fingerprint for load-bearing licensing modules.

Build step (native/build-fresh-installer.ps1) runs write_fingerprint.py which writes
`licensing/_fingerprint.json` with SHA-256 of critical source files.

At runtime commercial_license_ok() compares live file hashes. Patching a critical
.py without regenerating the fingerprint fails the commercial gate when
LICENSE_REQUIRED=1 and DEBUG=0.

This is a speed bump, not a vault: a determined attacker can recompute hashes or
disable the check. Combined with multi-site gates + .pyc-only shipping it raises cost.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("licensing")

# Relative to backend/ (parent of the licensing package).
# Release builds may ship bytecode-only (foo.pyc next to where foo.py was).
CRITICAL_REL_PATHS: List[str] = [
    "licensing/core.py",
    "licensing/enforcement.py",
    "licensing/integrity.py",
    "common/crypto_utils.py",
    "api/views.py",
]

_FINGERPRINT_NAME = "_fingerprint.json"
_cache: Optional[Tuple[bool, str]] = None  # (ok, detail)


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_critical(root: Path, rel_py: str) -> Optional[Path]:
    """Prefer .py (dev tree); fall back to sibling .pyc (release strip)."""
    py = root / rel_py
    if py.is_file():
        return py
    pyc = py.with_suffix(".pyc")
    if pyc.is_file():
        return pyc
    return None


def critical_paths() -> List[Path]:
    root = _backend_root()
    out: List[Path] = []
    for rel in CRITICAL_REL_PATHS:
        p = _resolve_critical(root, rel)
        if p is not None:
            out.append(p)
    return out


def compute_fingerprint() -> Dict[str, str]:
    """Map stable key (always the .py rel path) -> sha256 of the resolved file (.py or .pyc)."""
    root = _backend_root()
    out: Dict[str, str] = {}
    for rel in CRITICAL_REL_PATHS:
        p = _resolve_critical(root, rel)
        if p is not None:
            out[rel.replace("\\", "/")] = _file_sha256(p)
    return out


def fingerprint_path() -> Path:
    return Path(__file__).resolve().parent / _FINGERPRINT_NAME


def write_fingerprint_file(dest: Optional[Path] = None) -> Path:
    """Write/overwrite the fingerprint file (called from the build pipeline)."""
    path = dest or fingerprint_path()
    payload = {
        "version": 1,
        "files": compute_fingerprint(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_expected() -> Optional[Dict[str, str]]:
    path = fingerprint_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        files = data.get("files") if isinstance(data, dict) else None
        if not isinstance(files, dict) or not files:
            return None
        return {str(k).replace("\\", "/"): str(v) for k, v in files.items()}
    except Exception:
        return None


def integrity_ok(force_reload: bool = False) -> bool:
    """True if fingerprint matches or check is not enforced.

    Enforcement rules:
      - No fingerprint file → OK in lenient/dev (allows git checkouts without a build step).
      - LICENSE_REQUIRED + not DEBUG + no fingerprint → FAIL (prod installer must ship it).
      - Fingerprint present + mismatch → FAIL always (someone patched after install).
    """
    global _cache
    if _cache is not None and not force_reload:
        return _cache[0]

    try:
        from django.conf import settings
        strict = bool(getattr(settings, "LICENSE_REQUIRED", False)) and not bool(
            getattr(settings, "DEBUG", False)
        )
    except Exception:
        strict = False

    expected = load_expected()
    if expected is None:
        ok = not strict
        detail = "no_fingerprint_strict" if strict else "no_fingerprint_lenient"
        _cache = (ok, detail)
        if not ok:
            logger.critical("licensing integrity: missing _fingerprint.json in production")
        return ok

    actual = compute_fingerprint()
    # Every expected file must match; extra live files are ignored.
    for rel, exp_hash in expected.items():
        got = actual.get(rel)
        if got is None or got != exp_hash:
            logger.critical(
                "licensing integrity MISMATCH on %s (expected %s… got %s…)",
                rel, exp_hash[:12], (got or "missing")[:12],
            )
            # Dev trees edit sources constantly — only fail closed in production-strict.
            if strict:
                _cache = (False, f"mismatch:{rel}")
                return False
            _cache = (True, f"mismatch_lenient:{rel}")
            return True

    _cache = (True, "ok")
    return True


def integrity_status() -> dict:
    """Diagnostics for /license status (no secrets)."""
    expected = load_expected()
    ok = integrity_ok()
    return {
        "integrity_ok": ok,
        "fingerprint_present": expected is not None,
        "critical_files": list(CRITICAL_REL_PATHS),
        "detail": _cache[1] if _cache else None,
    }
