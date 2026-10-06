"""Background thread of the web server process that runs the periodic notification
checks every minute (the server update check every 6 hours). Started explicitly by
serve.py (production) or by `runserver` (development) — never by migrations, tests or
the discovery service."""
import logging
import threading
import time

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 60
UPDATE_EVERY_SECONDS = 6 * 60 * 60
FIRST_DELAY_SECONDS = 15

_started = False
_lock = threading.Lock()


def _loop():
    from django.db import close_old_connections

    from .checks import run_all

    time.sleep(FIRST_DELAY_SECONDS)
    next_update = 0.0
    while True:
        started = time.monotonic()
        include_update = started >= next_update
        try:
            close_old_connections()
            run_all(include_update=include_update)
        except Exception:  # pragma: no cover - keep the thread alive
            log.exception("notification checks failed")
        finally:
            close_old_connections()
        if include_update:
            next_update = started + UPDATE_EVERY_SECONDS
        time.sleep(max(1.0, INTERVAL_SECONDS - (time.monotonic() - started)))


def start_worker():
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, name="lp-notifications", daemon=True).start()
