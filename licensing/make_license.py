"""Offline emergency issuer for the same strict .lpl contract as LabelPilot Sales.

The primary issuer is the Sales Edge service. This CLI accepts only a machine-bound
license and only a private key matching the public key embedded in this server tree.
Key and output paths must stay outside the repository.
"""
from __future__ import annotations

import argparse
import base64
import datetime
import json
import os
import re
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPOSITORY_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))
from licensing.core import LICENSE_PUBLIC_KEY_HEX  # noqa: E402

CONTROL = re.compile(r"[\x00-\x1f\x7f]")
LICENSE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,79}\Z")
MACHINE_ID = re.compile(r"[0-9a-f]{32}\Z")
FEATURE = re.compile(r"[A-Za-z0-9._:-]{1,64}\Z")


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def external_path(value: str, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    try:
        path.relative_to(REPOSITORY_ROOT)
    except ValueError:
        return path
    raise ValueError(f"{label} must be outside the server repository")


def bounded_text(value: str, label: str, maximum: int) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum or CONTROL.search(text):
        raise ValueError(f"invalid {label}")
    return text


def iso_date(value: str, label: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value or ""):
        raise ValueError(f"{label} must be YYYY-MM-DD")
    parsed = datetime.date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError(f"invalid {label}")
    return value


def utc_today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def edition(max_stations: int | None, expires: str | None) -> str:
    seats = "unlimited" if max_stations is None else f"{max_stations}-station"
    return f"{'lifetime' if expires is None else 'subscription'}-{seats}"


def read_production_private_key(path: Path) -> Ed25519PrivateKey:
    raw = path.read_text(encoding="ascii").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", raw):
        raise ValueError("private key must be 64 hexadecimal characters")
    private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(raw))
    public_hex = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    ).hex()
    if not secrets.compare_digest(public_hex, LICENSE_PUBLIC_KEY_HEX):
        raise ValueError("private key does not match the public key embedded in the product")
    return private_key


def atomic_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        if os.name != "nt":
            temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def command_genkey(args) -> None:
    output = external_path(args.private_out, "private key path")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing key: {output}")
    private_key = Ed25519PrivateKey.generate()
    private_hex = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    ).hex()
    public_hex = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    ).hex()
    atomic_write(output, private_hex + "\n")
    print(f"Private key written outside repository: {output}")
    print(f"Public key: {public_hex}")


def command_issue(args) -> None:
    private_path = external_path(args.private, "private key path")
    output = external_path(args.out, "license output path")
    private_key = read_production_private_key(private_path)

    customer = bounded_text(args.customer, "customer", 160)
    machine_id = args.machine_id.strip().lower()
    if not MACHINE_ID.fullmatch(machine_id):
        raise ValueError("machine-id must contain 32 lowercase hexadecimal characters")
    if args.max_stations is not None and not 1 <= args.max_stations <= 100_000:
        raise ValueError("max-stations must be in the range 1..100000")
    if not 1 <= args.key_version <= 1_000_000:
        raise ValueError("key-version must be in the range 1..1000000")

    issued = iso_date(args.issued or utc_today(), "issued")
    expires = iso_date(args.expires, "expires") if args.expires else None
    if expires is not None and expires < issued:
        raise ValueError("expires cannot be earlier than issued")
    license_id = bounded_text(
        args.license_id or f"LP-{issued.replace('-', '')}-{secrets.token_hex(8).upper()}",
        "license-id",
        80,
    )
    if not LICENSE_ID.fullmatch(license_id):
        raise ValueError("invalid license-id")
    feature_values = [] if not args.features else [item.strip() for item in args.features.split(",")]
    if len(feature_values) > 64 or any(not FEATURE.fullmatch(item) for item in feature_values):
        raise ValueError("invalid feature list")
    feature_values = list(dict.fromkeys(feature_values))

    payload = {
        "customer": customer,
        "license_id": license_id,
        "issued": issued,
        "expires": expires,
        "max_stations": args.max_stations,
        "machine_id": machine_id,
        "key_version": args.key_version,
        "edition": bounded_text(args.edition or edition(args.max_stations, expires), "edition", 120),
        "features": feature_values,
    }
    payload_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    token = f"{b64url(payload_bytes)}.{b64url(private_key.sign(payload_bytes))}"
    atomic_write(output, token)
    print(f"License written: {output}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="LabelPilot offline emergency license issuer")
    commands = parser.add_subparsers(dest="command", required=True)

    keygen = commands.add_parser("genkey")
    keygen.add_argument("--private-out", required=True)
    keygen.set_defaults(handler=command_genkey)

    issue = commands.add_parser("issue")
    issue.add_argument("--private", required=True)
    issue.add_argument("--customer", required=True)
    issue.add_argument("--machine-id", required=True)
    issue.add_argument("--max-stations", type=int)
    issue.add_argument("--expires")
    issue.add_argument("--features")
    issue.add_argument("--edition")
    issue.add_argument("--license-id")
    issue.add_argument("--key-version", type=int, default=1)
    issue.add_argument("--issued")
    issue.add_argument("--out", required=True)
    issue.set_defaults(handler=command_issue)

    args = parser.parse_args(argv)
    try:
        args.handler(args)
        return 0
    except Exception as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
