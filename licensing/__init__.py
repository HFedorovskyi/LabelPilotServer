"""Offline signed-license layer (Phase 0).

A valid Ed25519-signed license is LOAD-BEARING: the data-encryption key used by
common.crypto_utils is derived from the verified license bytes, so removing or
forging the license yields a wrong key and client payloads stop decrypting.
Seat (max_stations) and expiry limits are read from the same verified license.

Public API:
    load_license() -> License | None
    derive_data_key(license) -> bytes
    seat_available(current_count) -> bool
    seat_limit() -> int | None
    license_status() -> dict
    machine_id() -> str
"""
from .core import (
    License,
    LicenseError,
    LicenseState,
    load_license,
    license_state,
    derive_data_key,
    seat_available,
    seat_limit,
    license_status,
    machine_id,
)

__all__ = [
    "License",
    "LicenseError",
    "LicenseState",
    "load_license",
    "license_state",
    "derive_data_key",
    "seat_available",
    "seat_limit",
    "license_status",
    "machine_id",
]
