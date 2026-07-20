#!/usr/bin/env python3
"""Generate licensing/_fingerprint.json for the release build.

Usage (from backend/ or repo root):
  python -m licensing.write_fingerprint
  python licensing/write_fingerprint.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a script without installing the package.
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from licensing.integrity import write_fingerprint_file, compute_fingerprint  # noqa: E402


def main() -> int:
    path = write_fingerprint_file()
    files = compute_fingerprint()
    print(f"Wrote {path} ({len(files)} files)")
    for rel, h in sorted(files.items()):
        print(f"  {rel}: {h[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
