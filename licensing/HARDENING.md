# License hardening (server)

Production licensing is offline and fail-closed at three independent boundaries.

DEBUG=false always activates the production boundary. LICENSE_REQUIRED=true may force it during commissioning with DEBUG enabled, but LICENSE_REQUIRED=false never downgrades a production process.

| Layer | Location | Enforced behavior |
|---|---|---|
| License signature | `backend/licensing/core.py` | Ed25519, canonical payload, exact field contract, machine binding, expiry and entitlement bounds |
| Native decision | `native/license-guard` | Independently verifies the license and the signed backend manifest before commercial actions |
| Backend manifest | `backend/licensing/_fingerprint.lpf` | Vendor-signed hash/size list for every shipped Python module; unsigned Python code is rejected |
| Release envelope | `_release.lpr` | Vendor-signed guard, updater, runtime scripts, backend manifest, versions and wheels |
| Runtime gate | `backend/licensing/enforcement.py` | Native and Python checks must agree before export/encryption |
| Update gate | `updater/updater_service.py` | ZIP layout and both signatures are checked before services stop; customer state is preserved |
| Filesystem boundary | `native/install-services.ps1` | Runtime is read/execute for interactive users and writable only by SYSTEM/Administrators |

## Key separation

- Customer licenses use `LABELPILOT_LICENSE_PRIVATE_KEY` in the Sales Edge environment.
- Release manifests use a separate offline integrity key.
- Installer download tickets use `DOWNLOAD_TICKET_SECRET`; they never reuse either signing key.
- Only public keys are embedded in deliverables.

## Build

Run `native/build-fresh-installer.ps1` or `native/build-update-zip.ps1` with `LABELPILOT_INTEGRITY_PRIVATE_KEY_FILE` pointing to the external integrity key. The build compiles protected modules, removes the protected Python sources from staging, signs `_fingerprint.lpf` and `_release.lpr`, then verifies both with the staged native guard.

The first upgrade from a pre-hardening build must use the full installer. Later ZIP updates are accepted only when signed by the trusted integrity key.

## Verification

- `cargo test --locked --manifest-path native/license-guard/Cargo.toml`
- Python license-contract tests cover malformed signed payloads, non-canonical JSON/base64url and wrong signatures.
- Update preflight tests cover valid signed packages, tampered updater code and injected paths.

A release is invalid if a guard, manifest, runtime script, wheel or Python module differs from its signed record.
