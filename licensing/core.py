"""Offline signed-license core.

License file `license.lpl` lives next to .env in the backend dir. Format (JWT-ish):
    <b64url(payload_json)>.<b64url(ed25519_signature_over_payload_json)>

The PUBLIC key is embedded below; the matching PRIVATE key lives ONLY on the
the Sales signing service. Verification, key-derivation,
and limits are all offline — no network needed (online activation is a later layer).

Load-bearing design: derive_data_key() feeds common.crypto_utils.get_key(), so a
valid license is REQUIRED to produce the real data key. With NO license present
(pre-licensing installs) crypto_utils falls back to the legacy key so nothing
breaks; once a license is issued, tampering with it changes the derived key.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .clock import GRACE_DAYS, read_clock

# Ed25519 public key (hex of the 32-byte raw key). Production key (2026) — must match the desktop
# client (encryption.ts LICENSE_PUBLIC_KEY_HEX) and the LABELPILOT_LICENSE_PUBLIC_KEY used to sign.
LICENSE_PUBLIC_KEY_HEX = "bd770682b1bef5aa9c081320dad25e7e1c81752e357bdeb36d9016b4afe45e56"

_LICENSE_FILENAME = "license.lpl"
_LICENSE_TOKEN_LIMIT = 64 * 1024
_LICENSE_FIELDS = {
    "customer", "license_id", "issued", "expires", "max_stations",
    "machine_id", "key_version", "edition", "features",
}
_LICENSE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,79}\Z")
_MACHINE_ID_RE = re.compile(r"[0-9a-f]{32}\Z")
_FEATURE_RE = re.compile(r"[A-Za-z0-9._:-]{1,64}\Z")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _b64url_decode(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("license contains non-canonical base64url")
    decoded = base64.b64decode(
        value + "=" * (-len(value) % 4), altchars=b"-_", validate=True,
    )
    if b64url_encode(decoded) != value:
        raise ValueError("license contains non-canonical base64url")
    return decoded


def b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _today_utc() -> datetime.date:
    """Today's date in the app's timezone (settings TIME_ZONE=UTC, USE_TZ=True), so an
    `expires` date isn't tripped a day early/late by the server's OS-local clock. Falls
    back to the OS-local date when Django isn't configured (keeps this module import-pure)."""
    try:
        from django.utils import timezone
        return timezone.now().date()
    except Exception:
        return datetime.date.today()


@dataclass
class License:
    customer: str
    license_id: str
    issued: Optional[str]
    expires: Optional[str]        # ISO date "YYYY-MM-DD" or None = lifetime
    max_stations: Optional[int]   # None = unlimited
    machine_id: str               # required 32-char machine binding
    key_version: int
    edition: str
    features: list
    payload_bytes: bytes          # exact signed bytes — the HKDF input keying material
    token: str                    # the raw license-file token (b64url(payload).b64url(sig))

    def is_expired(self, today: Optional[datetime.date] = None) -> bool:
        """Past the expiry date (the grace period may still be running)."""
        if not self.expires:
            return False
        try:
            exp = datetime.date.fromisoformat(self.expires)
        except (ValueError, TypeError):
            return True  # malformed expiry -> fail safe (treat as expired)
        return (today or _today_utc()) > exp

    def grace_until(self) -> Optional[datetime.date]:
        """Last day the commercial gates still accept an expired subscription."""
        if not self.expires:
            return None
        try:
            return datetime.date.fromisoformat(self.expires) + datetime.timedelta(days=GRACE_DAYS)
        except (ValueError, TypeError):
            return None

    def is_past_grace(self, today: Optional[datetime.date] = None) -> bool:
        """Expired AND the grace period is over: exports and new seats stop.
        Printing on the stations never stops (no kill switch on production lines)."""
        if not self.is_expired(today):
            return False
        until = self.grace_until()
        return until is None or (today or _today_utc()) > until


def _license_path() -> Path:
    # backend/  (parent of the licensing package), next to .env / db.sqlite3
    return Path(__file__).resolve().parent.parent / _LICENSE_FILENAME


_MACHINE_ID_CACHE: Optional[str] = None


def machine_id() -> str:
    """Stable per-machine fingerprint (Windows MachineGuid; falls back to MAC).
    Shown to the customer so the vendor can issue a machine-bound license.

    The successful MachineGuid result is cached process-wide. If a later read transiently
    fails (registry locked/AV), we return the cached value rather than the UNSTABLE
    uuid.getnode() MAC fallback — getnode() may hand back a random locally-administered MAC
    that differs between calls, which would flip a bound license's machine_ok on/off mid-run
    (intermittently denying new exports/seats). Only a process that NEVER read the registry
    successfully falls through to the MAC."""
    global _MACHINE_ID_CACHE
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
            guid, _ = winreg.QueryValueEx(k, "MachineGuid")
            _MACHINE_ID_CACHE = hashlib.sha256(guid.encode()).hexdigest()[:32]
            return _MACHINE_ID_CACHE
    except Exception:
        if _MACHINE_ID_CACHE:
            return _MACHINE_ID_CACHE
        import uuid
        return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:32]


def _object_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate license field: {key}")
        result[key] = value
    return result


def _bounded_text(value, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    text = value.strip()
    if not text or len(text) > maximum or _CONTROL_RE.search(text):
        raise ValueError(f"{label} is empty, too long, or contains control characters")
    return text


def _parse_license_date(value, label: str) -> datetime.date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{label} must be YYYY-MM-DD")
    try:
        parsed = datetime.date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} is not a real calendar date") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{label} is not canonical")
    return parsed


def _verify_and_parse(raw: str) -> License:
    token = raw.strip()
    if not token or len(token.encode("utf-8")) > _LICENSE_TOKEN_LIMIT:
        raise ValueError("license token has an invalid size")
    parts = token.split(".")
    if len(parts) != 2 or not all(parts):
        raise ValueError("license token is malformed")
    payload_bytes = _b64url_decode(parts[0])
    signature = _b64url_decode(parts[1])
    if len(signature) != 64 or len(payload_bytes) > _LICENSE_TOKEN_LIMIT:
        raise ValueError("license signature or payload has an invalid size")
    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(LICENSE_PUBLIC_KEY_HEX))
    public_key.verify(signature, payload_bytes)

    payload = json.loads(
        payload_bytes.decode("utf-8"), object_pairs_hook=_object_without_duplicates,
    )
    if not isinstance(payload, dict) or set(payload) != _LICENSE_FIELDS:
        raise ValueError("license payload fields do not match the supported contract")
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    if canonical != payload_bytes:
        raise ValueError("license payload is not canonical JSON")

    customer = _bounded_text(payload["customer"], "customer", 160)
    license_id = _bounded_text(payload["license_id"], "license_id", 80)
    if not _LICENSE_ID_RE.fullmatch(license_id):
        raise ValueError("license_id has an invalid format")
    issued_date = _parse_license_date(payload["issued"], "issued")
    expires = payload["expires"]
    if expires is not None:
        expires_date = _parse_license_date(expires, "expires")
        if expires_date < issued_date:
            raise ValueError("expires cannot be earlier than issued")

    max_stations = payload["max_stations"]
    if max_stations is not None and (
        isinstance(max_stations, bool) or not isinstance(max_stations, int)
        or not 1 <= max_stations <= 100_000
    ):
        raise ValueError("max_stations must be null or a positive integer")
    machine = payload["machine_id"]
    if not isinstance(machine, str) or not _MACHINE_ID_RE.fullmatch(machine):
        raise ValueError("machine_id must be 32 lowercase hex characters")
    key_version = payload["key_version"]
    if (
        isinstance(key_version, bool) or not isinstance(key_version, int)
        or not 1 <= key_version <= 1_000_000
    ):
        raise ValueError("key_version must be a positive integer")
    edition = _bounded_text(payload["edition"], "edition", 120)
    features = payload["features"]
    if (
        not isinstance(features, list) or len(features) > 64
        or any(not isinstance(item, str) or not _FEATURE_RE.fullmatch(item) for item in features)
        or len(set(features)) != len(features)
    ):
        raise ValueError("features have an invalid format")

    return License(
        customer=customer,
        license_id=license_id,
        issued=payload["issued"],
        expires=expires,
        max_stations=max_stations,
        machine_id=machine,
        key_version=key_version,
        edition=edition,
        features=features,
        payload_bytes=payload_bytes,
        token=token,
    )

class LicenseError(RuntimeError):
    """Raised in production strict mode (DEBUG=false or LICENSE_REQUIRED=true) when a license is PRESENT but
    invalid (bad signature) — so the server fails CLOSED instead of silently falling
    back to the legacy key. An ABSENT license never raises (see crypto_utils.get_key)."""


@dataclass(frozen=True)
class LicenseState:
    present: bool          # a license.lpl file exists
    signature_valid: bool  # Ed25519 signature verified
    machine_ok: bool       # license is unbound, or bound to THIS machine
    expired: bool          # past its expiry date (judged at the trusted clock)
    license: Optional[License]  # the parsed License when signature_valid, else None
    past_grace: bool = False      # expired and the GRACE_DAYS grace period is over
    clock_rollback: bool = False  # the OS clock was turned back (see licensing.clock)
    today: Optional[datetime.date] = None  # the trusted date the facts above were judged at

    @property
    def in_grace(self) -> bool:
        return self.expired and not self.past_grace

    @property
    def valid_for_key(self) -> bool:
        """Whether the data key may be derived. Needs only a genuine (signature-valid)
        license — machine binding and expiry deliberately do NOT gate the key, so a
        transient machine_id() blip or a lapsed subscription can never brick decryption
        of existing data. Those gate ENFORCEMENT (seats) and warnings instead."""
        return self.present and self.signature_valid


_cache_lock = threading.Lock()
_cached_state = None  # (cache_key, LicenseState)


def license_state() -> LicenseState:
    """The SINGLE source of truth for license validity. Parses + verifies once per
    (mtime_ns, size) and caches, reporting present / signature_valid / machine_ok /
    expired as INDEPENDENT facts. get_key(), seat_available() and the UI all read this,
    so they can never diverge (the old bug: get_key ignored expiry, seat_available didn't).

    Expiry is judged on every call at the trusted clock (licensing.clock), never
    cached with the parse: a server running across its expiry date sees it."""
    parsed = _parsed_license()
    lic = parsed.license
    if lic is None:
        return parsed
    reading = read_clock(lic.issued)
    today = reading.today
    return LicenseState(
        present=parsed.present, signature_valid=parsed.signature_valid,
        machine_ok=parsed.machine_ok, license=lic,
        expired=lic.is_expired(today), past_grace=lic.is_past_grace(today),
        clock_rollback=reading.rollback, today=today,
    )


def _parsed_license() -> LicenseState:
    """Parse + verify license.lpl once per (mtime_ns, size); date facts are left unset."""
    path = _license_path()
    try:
        st = path.stat() if path.exists() else None
        # (mtime_ns, size) — not bare mtime: NTFS mtime granularity (~15ms) means a
        # same-tick license swap would otherwise keep serving the stale cached state.
        cache_key = (st.st_mtime_ns, st.st_size) if st else None
    except OSError:
        cache_key = None

    global _cached_state
    with _cache_lock:
        if _cached_state is not None and _cached_state[0] == cache_key:
            return _cached_state[1]

    present = cache_key is not None
    sig_ok = False
    machine_ok = True
    lic = None
    if present:
        try:
            lic = _verify_and_parse(path.read_text(encoding="utf-8"))
            sig_ok = True
            machine_ok = lic.machine_id == machine_id()
        except (InvalidSignature, ValueError, TypeError, json.JSONDecodeError, OSError):
            # Present but forged / corrupt / unparseable -> fail CLOSED (sig_ok stays
            # False). We deliberately do NOT serve a previously-cached good license: a
            # file replaced with garbage must never masquerade as valid. Torn reads
            # aren't a concern here — there is no live upload endpoint, and the updater
            # restores license.lpl with the service stopped.
            lic = None

    state = LicenseState(
        present=present, signature_valid=sig_ok, machine_ok=machine_ok,
        expired=False, license=lic if sig_ok else None,
    )
    with _cache_lock:
        _cached_state = (cache_key, state)
    return state


def load_license() -> Optional[License]:
    """The valid, machine-bound License, or None (absent / bad signature / wrong machine).
    Re-expressed on top of license_state() so there is exactly ONE parse+verify per
    (mtime_ns, size) and existing callers keep their contract."""
    st = license_state()
    return st.license if (st.valid_for_key and st.machine_ok) else None


# Fixed, public domain-separation salt. The SECRET in this derivation is the signed
# license bytes (the HKDF input keying material) — NOT server-only material like
# SECRET_KEY. This is deliberate: the Electron client must derive the SAME data key
# from the SAME license, so the derivation must use only material both sides have.
_DATA_KEY_SALT = b"labelpilot-data-key|salt|v1"


def derive_data_key(lic: License) -> bytes:
    """HKDF-SHA256 the data-encryption key from the license's STABLE identity
    (license_id + key_version) — deliberately NOT the full payload bytes.

    Why not payload_bytes: a subscription RENEWAL keeps the same license_id+key_version
    but changes `expires`/`issued` inside the signed payload. If those bytes fed the
    derivation, the key would change on every renewal and EVERY previously-encrypted
    file (.lpi/.lps/.lpr) would stop decrypting. Deriving from the stable identity makes
    renewal key-invariant. Tamper-resistance comes from the Ed25519 signature check
    (performed before we ever derive), not from feeding the payload in here. key_version
    lets us rotate the derivation later without bricking field installs. The Electron
    client derives the identical key from the same token."""
    seed = lic.license_id.encode("utf-8") + b"|kv" + str(lic.key_version).encode()
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_DATA_KEY_SALT,
        info=b"lpi-data-key|" + seed,
    ).derive(seed)


# ── enforcement helpers ──────────────────────────────────────────────────────

def seat_limit() -> Optional[int]:
    """Max stations allowed. None = unlimited (also when no license is present)."""
    lic = load_license()
    return lic.max_stations if lic else None


def seat_available(current_count: int) -> bool:
    """True if a NEW station may be registered.
    NO license -> UNLIMITED. The commercial boundary without a license is the data-export
    gate (the server won't push real station data without a license), NOT a station cap —
    so a prospect can stand up as many stations as they like and test with the built-in demo.
    A present-but-invalid (bad signature / expired / wrong-machine) license blocks new seats;
    a valid license honors its max_stations (None = unlimited)."""
    st = license_state()
    if not st.present:
        return True
    if not st.valid_for_key:      # present but bad signature
        return False
    if st.past_grace or not st.machine_ok:
        return False
    return st.license.max_stations is None or current_count < st.license.max_stations


def license_status() -> dict:
    """Machine-readable status for the UI / a /license endpoint.

    ``expired`` = the expiry date has passed; ``grace`` = it has, but the grace
    period still runs until ``grace_until``; ``days_left`` counts to the expiry
    date (or, in grace, to the end of the grace period)."""
    st = license_state()
    lic = st.license if (st.valid_for_key and st.machine_ok) else None
    if lic is None:
        return {
            "licensed": False, "mode": "demo", "edition": "demo",
            "customer": None, "expires": None, "expired": False,
            "grace": False, "grace_until": None, "days_left": None, "clock_rollback": False,
            "max_stations": None, "demo_max_stations": None,
            "license_id": None, "machine_id": machine_id(),
        }
    grace_until = lic.grace_until()
    days_left = None
    if lic.expires and st.today is not None:
        try:
            target = grace_until if st.in_grace else datetime.date.fromisoformat(lic.expires)
            days_left = max(0, (target - st.today).days)
        except (TypeError, ValueError):
            days_left = 0
    return {
        "licensed": True, "mode": "licensed", "edition": lic.edition, "customer": lic.customer,
        "expires": lic.expires, "expired": st.expired,
        "grace": st.in_grace, "grace_until": grace_until.isoformat() if grace_until else None,
        "days_left": days_left, "clock_rollback": st.clock_rollback,
        "max_stations": lic.max_stations, "demo_max_stations": None,
        "license_id": lic.license_id, "features": lic.features, "machine_id": machine_id(),
    }


