"""Vendor-side license generator. RUN THIS ON YOUR MACHINE ONLY.

The PRIVATE key must never ship with the product. Workflow:

  1) One time — generate a keypair and embed the public key:
       python make_license.py genkey --private-out C:/keys/vendor_private.key
     Write the private key OUTSIDE the repo (never under backend/ — the build would
     ship it). Paste the printed public key into core.py LICENSE_PUBLIC_KEY_HEX, rebuild.

  2) Per customer — issue a signed license file:
       python make_license.py issue --private vendor_private.key \
           --customer "ООО Мясокомбинат" --max-stations 5 --expires 2027-06-23 \
           --out license.lpl
     Omit --max-stations for UNLIMITED; omit --expires for LIFETIME.
     Add --machine-id <id> (the value the customer's server shows) to bind it.

  RENEWAL: to renew a subscription, re-issue with the SAME --license-id and
     --key-version and a new --expires. The derived data key depends ONLY on
     (license_id, key_version), so the renewed license decrypts all existing files.
     (Changing --key-version or --license-id rotates the key and strands old data.)

The customer drops license.lpl next to .env in the install (or uploads it via the UI).
"""
import argparse
import base64
import datetime
import json
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def cmd_genkey(args):
    sk = Ed25519PrivateKey.generate()
    sk_hex = sk.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    ).hex()
    pk_hex = sk.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    ).hex()
    out = args.private_out or "vendor_private.key"
    with open(out, "w", encoding="ascii") as f:
        f.write(sk_hex)
    print(f"Private key written to: {out}")
    print("  KEEP THIS SECRET. Never commit it, never ship it in the product.")
    print()
    print("Embed this PUBLIC key in licensing/core.py -> LICENSE_PUBLIC_KEY_HEX:")
    print(f"  {pk_hex}")


def _edition(max_stations, expires):
    seats = "unlimited" if max_stations is None else f"{max_stations}-station"
    term = "lifetime" if expires is None else "subscription"
    return f"{term}-{seats}"


def cmd_issue(args):
    with open(args.private, "r", encoding="ascii") as f:
        sk = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(f.read().strip()))

    if args.expires:
        # validate format early so a typo doesn't ship a never-expiring license
        datetime.date.fromisoformat(args.expires)

    license_id = args.license_id or (
        "LP-" + datetime.date.today().strftime("%Y%m%d") + "-" +
        "".join(ch for ch in args.customer if ch.isalnum())[:8].upper()
    )
    payload = {
        "customer": args.customer,
        "license_id": license_id,
        "issued": args.issued or datetime.date.today().isoformat(),
        "expires": args.expires,            # None = lifetime
        "max_stations": args.max_stations,  # None = unlimited
        "machine_id": args.machine_id,      # None = unbound
        "key_version": args.key_version,
        "edition": args.edition or _edition(args.max_stations, args.expires),
        "features": args.features.split(",") if args.features else [],
    }
    payload_bytes = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    sig = sk.sign(payload_bytes)
    token = _b64url(payload_bytes) + "." + _b64url(sig)

    out = args.out or "license.lpl"
    with open(out, "w", encoding="utf-8") as f:
        f.write(token)
    print(f"License written to: {out}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.machine_id is None:
        print()
        print("WARNING: issued UNBOUND (no --machine-id) — this license works on ANY machine.")
        print("  Anyone who obtains the file can use it. For the anti-sharing control, bind it:")
        print("  ask the customer to run `python manage.py show_machine_id` and re-issue with")
        print("  --machine-id <that id>.")


def main(argv=None):
    p = argparse.ArgumentParser(description="LabelPilot license generator")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("genkey", help="generate a signing keypair")
    g.add_argument("--private-out", help="path to write the private key (default vendor_private.key)")
    g.set_defaults(func=cmd_genkey)

    i = sub.add_parser("issue", help="issue a signed license file")
    i.add_argument("--private", required=True, help="path to the private key file")
    i.add_argument("--customer", required=True, help="customer name (free text)")
    i.add_argument("--max-stations", type=int, default=None, help="seat limit (omit = unlimited)")
    i.add_argument("--expires", default=None, help="YYYY-MM-DD (omit = lifetime)")
    i.add_argument("--machine-id", default=None, help="bind to one server's machine_id (omit = unbound)")
    i.add_argument("--features", default=None, help="comma-separated feature flags")
    i.add_argument("--edition", default=None, help="override the edition label")
    i.add_argument("--license-id", default=None, help="override the auto license id")
    i.add_argument("--key-version", type=int, default=1, help="key-derivation version")
    i.add_argument("--issued", default=None, help="ISO issue date (omit = today)")
    i.add_argument("--out", default=None, help="output path (default license.lpl)")
    i.set_defaults(func=cmd_issue)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
