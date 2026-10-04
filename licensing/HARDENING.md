# License hardening (server)

Production licensing is offline and fail-closed at three independent boundaries.

DEBUG=false always activates the production boundary. LICENSE_REQUIRED=true may force it during commissioning with DEBUG enabled, but LICENSE_REQUIRED=false never downgrades a production process.

| Layer | Location | Enforced behavior |
|---|---|---|
| License signature | `backend/licensing/core.py` | Ed25519, canonical payload, exact field contract, machine binding, expiry and entitlement bounds |
| Native decision | `native/license-guard` | Independently verifies the license and the signed backend manifest before commercial actions |
| Backend manifest | `backend/licensing/_fingerprint.lpf` | Vendor-signed hash/size list for every shipped Python module; unsigned Python code is rejected |
| Release envelope | `_release.lpr` | Vendor-signed guard, updater, runtime scripts, backend manifest, versions and wheels, plus one digest per runtime tree (`python/` required, `ghostscript/` when present) re-hashed by the guard before every backend start |
| Interpreter | `native/run-backend.cmd`, `run-discovery.cmd` | Python runs with `-E -s` and a bytecode cache outside the signed trees that is wiped on every start (planted `.pth`, `sitecustomize`, `PYTHON*` variables or `.pyc` files do not load) |
| Guard authenticity | `backend/licensing/native_guard.py` | The guard binary's hash must match the signed release manifest before its verdict is used; a stub guard is refused |
| Seat cap | `backend/licensing/seats.py` | Recomputed from the licence at every data export: only the first `max_stations` active stations in seat order receive data, so editing seat states in the database gains nothing |
| Seat list | `backend/licensing/seat_list.py`, stations 2.0.6+ | Licences with the `seat-list` feature: every LPI2 payload carries a vendor-signed list of station fingerprints (at most `max_stations`, 90 days valid). Stations refuse data unless their own fingerprint is listed; this server cannot sign lists |
| Runtime gate | `backend/licensing/enforcement.py` | Native and Python checks must agree before export/encryption |
| Update gate | `updater/updater_service.py` | ZIP layout and both signatures are checked before services stop; customer state is preserved |
| Filesystem boundary | `native/install-services.ps1` | Runtime is read/execute for interactive users and writable only by SYSTEM/Administrators |

These layers raise the cost of tampering; none of them can stop an administrator of the server machine who patches both the startup scripts and the Python bytecode. The seat list moves the seat boundary out of this machine: the list is signed by the sales service, which caps it at the licence's seats and spends the release allowance (max(2, seats) per 30 days) on removals, and the stations verify it themselves.

## Seat list

- The sales service (`seat-list` function) is the only signer. A list names `license_id`, the server's `machine_id`, `max_stations`, the sorted station fingerprints, `issued` and `expires`.
- Online servers renew it daily and a few seconds after every seat change. They prove themselves with a random secret created on the first request (`license-seats.link`); someone holding only a copy of the licence file cannot replace a customer's list. The owner resets the link in the customer cabinet after reinstalling the server.
- Offline servers download a request file (`/api/v1/license/seat-list/request/`), have it signed in the cabinet and import the list (`/api/v1/license/seat-list/import/`). Lists only replace older lists of the same licence and server.
- Stations keep the newest list they have seen and refuse data from a licence that requires a list unless their fingerprint is in a valid one; a station bound to such a licence also refuses data under another licence that does not carry a list for it.
- Residual risks: a superseded list stays valid until it expires (a modified server can keep sending it to a station that was removed), bounded by the release allowance; stations older than 2.0.6 do not check lists, so a flagged licence should only be issued once the site runs 2.0.6+ (the server already refuses data to stations without a fingerprint); an administrator of a station PC can patch the client binary.
- Printing never stops: without a valid list only new data stops reaching the stations.

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
- Seat-list tests verify the cross-language fixture shared with the sales service and the stations (`licensing/fixtures/seat-list-contract.json`).
- Update preflight tests cover valid signed packages, tampered updater code and injected paths.

A release is invalid if a guard, manifest, runtime script, wheel or Python module differs from its signed record.
