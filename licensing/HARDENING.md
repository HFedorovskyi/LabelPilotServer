# License hardening (server)

## What was added (2026-07)

Commercial protection is **offline** and multi-layered. It does **not** make cracking
impossible — it raises the cost of a casual patch.

| Layer | Where | What it does |
|-------|--------|----------------|
| Ed25519 `.lpl` | `licensing/core.py` | Cannot forge licenses without vendor private key |
| Export gate | `licensing/enforcement.py` + `api/views.py` | Fresh re-verify + machine + expiry |
| Crypto gate | `common/crypto_utils.encrypt_data` | In prod refuses blobs without commercial OK |
| Gather gate | `StationsViewSet._gather_sync_data` | Third call site even if view action forgot the gate |
| Integrity | `licensing/_fingerprint.json` | SHA-256 of critical modules; mismatch blocks export when `LICENSE_REQUIRED=1` |
| Bytecode strip | `native/build-fresh-installer.ps1` | Ships `.pyc` for licensing/crypto (no easy Notepad edit) |
| Prod defaults | `native/install-services.ps1` | `LICENSE_REQUIRED=1`, `DJANGO_DEBUG=0` |

## Dev vs prod

| | Dev (`DJANGO_DEBUG=1` or no fingerprint) | Prod installer |
|--|------------------------------------------|----------------|
| Export without license | Denied (always) | Denied |
| Integrity mismatch | Lenient if no fingerprint | Fail closed |
| `encrypt_data` without license | Allowed (legacy key) | Denied when `LICENSE_REQUIRED=1` |

## Build checklist

1. Change licensing / crypto / export code as needed.
2. Run `python backend/licensing/write_fingerprint.py` in dev if you want local fingerprint.
3. Build installer via `native/build-fresh-installer.ps1` — it **recompiles, strips, fingerprints** the stage automatically.
4. Ship the new Setup EXE; existing installs keep their `.env` (script appends `LICENSE_REQUIRED=1` if missing).

## Client (Electron)

- Licensed stations reject **plaintext** LAN pushes and **plaintext** USB files (LPI2 only).
- Demo / unprovisioned stations still accept plain JSON for first run.

## Honest limits

A skilled reverse engineer can still patch Python bytecode or replace the whole
binary. Stronger options later: Nuitka for the whole backend, online license
heartbeat, code signing + SmartScreen.
