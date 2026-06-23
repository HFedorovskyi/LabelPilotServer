"""Production entry point — runs the Django app under Waitress (Windows-native WSGI).

Used by the native Windows service (run-backend.cmd) instead of Docker/gunicorn.
Static files are served by WhiteNoise; the frontend SPA is served from FRONTEND_DIST.
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LabelPilotServer.settings")

from waitress import serve  # noqa: E402
from LabelPilotServer.wsgi import application  # noqa: E402


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    threads = int(os.getenv("WAITRESS_THREADS", "8"))
    print(f"LabelPilot backend (Waitress) serving on http://{host}:{port}")
    serve(application, host=host, port=port, threads=threads)


if __name__ == "__main__":
    main()
