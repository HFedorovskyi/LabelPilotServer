"""Keep the updater service (LabelPilotUpdater) on its current code. The updater does not
restart after an update it applied up to 1.1.34, so after an update from 1.1.34 the old
updater would keep running until the computer restarts — listening on the network, taking
browser requests, without backups on request. Once it is idle, the server restarts that
service through NSSM. Newer updaters restart themselves after an update (api level 2+).
Windows installs only (serve.py), best effort: never stops the server."""
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

API_LEVEL = 2            # what this server needs (updater_service.API_LEVEL)
FIRST_LOOK = 90          # after the server starts: the updater that started it finishes first
RETRY = 60
ATTEMPTS = 10
NSSM = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "nssm" / "nssm.exe"


def _updater():
    from api.system_views import UPDATER
    return UPDATER


def check_once() -> str:
    """One look: "current", "busy", "restarted", "down" or "failed"."""
    base = _updater()
    try:
        status = requests.get(f"{base}/status", timeout=5).json()
    except (requests.RequestException, ValueError):
        return "down"
    if int(status.get("api") or 1) >= API_LEVEL:
        return "current"
    try:
        progress = requests.get(f"{base}/update/progress", timeout=5).json()
    except (requests.RequestException, ValueError):
        return "down"
    if progress.get("status") == "running":
        return "busy"
    if not NSSM.exists():
        return "failed"
    result = subprocess.run([str(NSSM), "restart", "LabelPilotUpdater"], capture_output=True, timeout=60)
    if result.returncode != 0:
        log.warning("could not restart the updater: %s", result.stderr[:300])
        return "failed"
    log.info("restarted the outdated updater service")
    return "restarted"


def ensure_in_background() -> None:
    if sys.platform != "win32":
        return

    def run():
        time.sleep(FIRST_LOOK)
        for _ in range(ATTEMPTS):
            try:
                outcome = check_once()
            except Exception:  # pragma: no cover - best effort, logged
                log.exception("updater upkeep failed")
                return
            if outcome != "busy" and outcome != "down":
                return
            time.sleep(RETRY)

    threading.Thread(target=run, name="updater-upkeep", daemon=True).start()
