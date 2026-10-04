"""Verify the vendor-signed integrity manifest shipped with production builds."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = logging.getLogger("licensing")

INTEGRITY_PUBLIC_KEY_HEX = (
    "c117721acecaad66796887afb01de4a8ae5cb6ca7bcfbaaad3eed8f86910b901"
)
MANIFEST_KIND = "labelpilot-integrity-v2"
MANIFEST_VERSION = 2
MANIFEST_FILENAME = "_fingerprint.lpf"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_MANIFEST_FILES = 4096
CACHE_SECONDS = 5.0

REQUIRED_FILE_GROUPS = (
    ("licensing/core.py", "licensing/core.pyc"),
    ("licensing/enforcement.py", "licensing/enforcement.pyc"),
    ("licensing/integrity.py", "licensing/integrity.pyc"),
    ("licensing/native_guard.py", "licensing/native_guard.pyc"),
    ("common/crypto_utils.py", "common/crypto_utils.pyc"),
    ("api/views.py", "api/views.pyc"),
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_B64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_cache: Optional[Tuple[float, tuple, bool, str, Optional[dict]]] = None


class IntegrityError(RuntimeError):
    """A signed manifest or one of its protected files is invalid."""


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent


def fingerprint_path() -> Path:
    return Path(__file__).resolve().parent / MANIFEST_FILENAME


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


def _b64url_decode(value: str, label: str) -> bytes:
    if not value or not _B64URL.fullmatch(value):
        raise IntegrityError(f"{label} is not canonical base64url")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise IntegrityError(f"{label} is malformed") from exc
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if canonical != value:
        raise IntegrityError(f"{label} is not canonical base64url")
    return decoded


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise IntegrityError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_signed_manifest(path: Path) -> dict:
    payload = _verify_signed_payload(path)
    _validate_contract(payload)
    return payload


def _verify_signed_payload(path: Path) -> dict:
    """Signature-checked JSON payload of a vendor-signed manifest (any kind)."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise IntegrityError(f"manifest is unreadable: {exc}") from exc
    if size <= 0 or size > MAX_MANIFEST_BYTES:
        raise IntegrityError("manifest size is outside the accepted range")
    try:
        token = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise IntegrityError(f"manifest is unreadable: {exc}") from exc
    parts = token.split(".")
    if len(parts) != 2:
        raise IntegrityError("manifest token is malformed")
    payload_bytes = _b64url_decode(parts[0], "manifest payload")
    signature = _b64url_decode(parts[1], "manifest signature")
    if len(signature) != 64:
        raise IntegrityError("manifest signature has the wrong length")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(INTEGRITY_PUBLIC_KEY_HEX)
        )
        public_key.verify(signature, payload_bytes)
    except (InvalidSignature, ValueError) as exc:
        raise IntegrityError("manifest signature is invalid") from exc
    try:
        payload = json.loads(
            payload_bytes.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise IntegrityError("manifest payload is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise IntegrityError("manifest payload is not an object")
    return payload


RELEASE_MANIFEST_FILENAME = "_release.lpr"
RELEASE_MANIFEST_KIND = "labelpilot-release-v1"
GUARD_RELEASE_PATHS = ("tools/labelpilot-license-guard.exe", "tools/labelpilot-license-guard")


def release_manifest_path() -> Path:
    """<install root>/_release.lpr; the backend lives at <install root>/app/backend."""
    return _backend_root().parent.parent / RELEASE_MANIFEST_FILENAME


def signed_guard_record() -> Optional[dict]:
    """The license guard's signed {"sha256", "size"} from the release manifest, or
    None where no release manifest exists (a source tree). Raises IntegrityError
    when the manifest is present but forged, foreign or incomplete."""
    path = release_manifest_path()
    if not path.is_file():
        return None
    payload = _verify_signed_payload(path)
    if payload.get("kind") != RELEASE_MANIFEST_KIND or payload.get("product") != "labelpilot-server":
        raise IntegrityError("unsupported release manifest")
    files = payload.get("files")
    if not isinstance(files, dict):
        raise IntegrityError("release manifest file map is invalid")
    for relative in GUARD_RELEASE_PATHS:
        record = files.get(relative)
        if isinstance(record, dict) and isinstance(record.get("sha256"), str) and isinstance(record.get("size"), int):
            return {"sha256": record["sha256"].lower(), "size": record["size"]}
    raise IntegrityError("release manifest does not sign the license guard")


def file_digest(path: Path) -> Tuple[int, str]:
    return _file_sha256(path)


def _normalize_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise IntegrityError(f"unsafe manifest path: {value!r}")
    if value.startswith("/"):
        raise IntegrityError(f"unsafe manifest path: {value!r}")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise IntegrityError(f"unsafe manifest path: {value!r}")
    return value


def _validate_contract(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise IntegrityError("manifest payload is not an object")
    if (
        payload.get("kind") != MANIFEST_KIND
        or payload.get("manifest_version") != MANIFEST_VERSION
        or payload.get("product") != "labelpilot-server"
    ):
        raise IntegrityError("unsupported integrity manifest")
    release_version = payload.get("release_version")
    issued_at = payload.get("issued_at")
    if not isinstance(release_version, str) or not release_version or len(release_version) > 64:
        raise IntegrityError("manifest release version is invalid")
    if not isinstance(issued_at, str) or not issued_at:
        raise IntegrityError("manifest issued_at is invalid")
    files = payload.get("files")
    if not isinstance(files, dict) or not 0 < len(files) <= MAX_MANIFEST_FILES:
        raise IntegrityError("manifest file map is invalid")
    signed_paths = {_normalize_relative(relative) for relative in files}
    for group in REQUIRED_FILE_GROUPS:
        if not any(candidate in signed_paths for candidate in group):
            raise IntegrityError(f"manifest omits critical group: {' | '.join(group)}")
    for relative, expected in files.items():
        _normalize_relative(relative)
        if not isinstance(expected, dict):
            raise IntegrityError(f"manifest entry is invalid: {relative}")
        digest = expected.get("sha256")
        size = expected.get("size")
        if (
            not isinstance(digest, str)
            or not _HEX_64.fullmatch(digest)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
        ):
            raise IntegrityError(f"manifest entry is invalid: {relative}")


def _resolve_regular_file(root: Path, relative: str) -> Path:
    relative = _normalize_relative(relative)
    candidate = root.joinpath(*relative.split("/"))
    cursor = root
    for part in relative.split("/"):
        cursor = cursor / part
        try:
            if cursor.is_symlink():
                raise IntegrityError(f"manifest path contains a symlink: {relative}")
        except OSError as exc:
            raise IntegrityError(f"manifest path is unreadable: {relative}: {exc}") from exc
    if not candidate.is_file():
        raise IntegrityError(f"protected file is missing: {relative}")
    try:
        canonical = candidate.resolve(strict=True)
        canonical.relative_to(root)
    except (OSError, ValueError) as exc:
        raise IntegrityError(f"manifest path escapes root: {relative}") from exc
    return canonical


def _file_sha256(path: Path) -> Tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _actual_python_code(root: Path) -> set[str]:
    output: set[str] = set()
    skipped = {"__pycache__", "media", "staticfiles", "logs", ".git"}
    for directory, directories, filenames in __import__("os").walk(root, followlinks=False):
        directory_path = Path(directory)
        kept = []
        for name in directories:
            child = directory_path / name
            if name in skipped:
                continue
            if child.is_symlink():
                raise IntegrityError(f"code directory is a symlink: {child}")
            kept.append(name)
        directories[:] = kept
        for name in filenames:
            path = directory_path / name
            if path.suffix not in {".py", ".pyc"}:
                continue
            if path.is_symlink() or not path.is_file():
                raise IntegrityError(f"code file is not regular: {path}")
            output.add(path.relative_to(root).as_posix())
    return output


def verify_signed_manifest() -> dict:
    root = _backend_root().resolve(strict=True)
    payload = _parse_signed_manifest(fingerprint_path())
    for relative, expected in payload["files"].items():
        actual_size, actual_hash = _file_sha256(_resolve_regular_file(root, relative))
        if actual_size != expected["size"] or actual_hash != expected["sha256"]:
            raise IntegrityError(f"integrity hash mismatch: {relative}")
    unsigned = _actual_python_code(root) - set(payload["files"])
    if unsigned:
        raise IntegrityError(f"unsigned Python code: {sorted(unsigned)[0]}")
    return payload


def _state_key() -> tuple:
    root = _backend_root()
    paths = [fingerprint_path()]
    for group in REQUIRED_FILE_GROUPS:
        for relative in group:
            candidate = root.joinpath(*relative.split("/"))
            if candidate.is_file():
                paths.append(candidate)
                break
    state = []
    for path in paths:
        try:
            stat = path.stat()
            state.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            state.append((str(path), None, None))
    return tuple(state)


def load_expected() -> Optional[Dict[str, dict]]:
    """Compatibility helper: return the signed file map, or None if absent/invalid."""
    try:
        return _parse_signed_manifest(fingerprint_path())["files"]
    except IntegrityError:
        return None


def integrity_ok(force_reload: bool = False) -> bool:
    """Validate signature, contract, and hashes; production fails closed."""
    global _cache
    now = time.monotonic()
    key = _state_key()
    if (
        not force_reload
        and _cache is not None
        and now - _cache[0] < CACHE_SECONDS
        and _cache[1] == key
    ):
        return _cache[2]

    strict = _strict_mode()
    manifest = fingerprint_path()
    if not manifest.is_file():
        ok = not strict
        detail = "missing_manifest_strict" if strict else "missing_manifest_lenient"
        payload = None
    else:
        try:
            payload = verify_signed_manifest()
            ok = True
            detail = "ok"
        except Exception as exc:
            ok = not strict
            detail = f"invalid_manifest_{'strict' if strict else 'lenient'}:{exc}"
            payload = None
            if strict:
                logger.critical("licensing signed integrity failed: %s", exc)
            else:
                logger.warning("licensing signed integrity ignored in development: %s", exc)
    _cache = (now, key, ok, detail, payload)
    return ok


def integrity_status() -> dict:
    ok = integrity_ok()
    payload = _cache[4] if _cache else None
    return {
        "integrity_ok": ok,
        "fingerprint_present": fingerprint_path().is_file(),
        "signature_valid": bool(payload),
        "manifest_version": payload.get("manifest_version") if payload else None,
        "release_version": payload.get("release_version") if payload else None,
        "protected_files": sorted(payload.get("files", {})) if payload else [],
        "detail": _cache[3] if _cache else None,
    }
