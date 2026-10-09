"""Server updates and backups for «Настройки». The updater service (LabelPilotUpdater) listens
on 127.0.0.1 only; the admin panel reaches it through these views, so updates work from any
computer and nobody can start one, a rollback or a backup without signing in as an
administrator. Reading the state is open to every signed-in user."""
import os
import time
import uuid

import requests
from django.conf import settings
from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.i18n import tr
from api.permissions import IsAdmin

# LP_UPDATER_URL: a test stand on a computer that also runs a real install points this at a
# stand-in, so its buttons can never update or roll back the real server.
UPDATER = os.getenv("LP_UPDATER_URL", "http://127.0.0.1:9000").rstrip("/")
CHECK_KEY = "system:update-check"
CHECK_TTL = 10 * 60          # GitHub is asked at most every 10 minutes...
REFRESH_GAP = 30             # ...or on «Проверить сейчас», not more often than this


class UpdaterDown(Exception):
    pass


def _call(method, path, timeout=15, **kwargs):
    try:
        return requests.request(method, f"{UPDATER}{path}", timeout=timeout, **kwargs)
    except requests.RequestException as e:
        raise UpdaterDown(str(e)) from e


def _passthrough(res):
    try:
        body = res.json()
    except ValueError:
        body = {"detail": res.text[:500]}
    return Response(body, status=res.status_code)


def _down():
    return Response({"detail": tr("system.updaterDown"), "updater": "offline"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class UpdateView(APIView):
    """GET: this version and whether a newer one is out (cached). POST: update online."""

    def get_permissions(self):
        return [IsAdmin()] if self.request.method == "POST" else [IsAuthenticated()]

    def get(self, request):
        cached = cache.get(CHECK_KEY)
        refresh = request.query_params.get("refresh") == "1"
        if cached and (not refresh or time.time() - cached["checked_ts"] < REFRESH_GAP):
            return Response(cached)
        result = {"current": settings.VERSION, "checked_ts": time.time(), "updater": "online",
                  "available": None, "version": "", "changelog": "", "published_at": "", "has_package": False, "error": ""}
        try:
            res = _call("GET", "/check")
        except UpdaterDown:
            result["updater"] = "offline"
        else:
            if res.ok:
                data = res.json()
                result.update(available=bool(data.get("available")), version=data.get("version") or "",
                              changelog=data.get("changelog") or "", published_at=data.get("published_at") or "",
                              has_package=bool(data.get("download_url")))
            else:
                # The updater runs, but GitHub is out of reach (no internet on the plant network).
                result["error"] = "offline"
        cache.set(CHECK_KEY, result, CHECK_TTL)
        return Response(result)

    def post(self, request):
        try:
            res = _call("POST", "/update", timeout=30)
        except UpdaterDown:
            return _down()
        cache.delete(CHECK_KEY)
        return _passthrough(res)


def _multipart(upload, boundary):
    """Stream the uploaded .lpupdate to the updater without holding it in memory."""
    name = (upload.name or "update.lpupdate").replace('"', "")
    yield (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
           "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8")
    for chunk in upload.chunks(1024 * 1024):
        yield chunk
    yield f"\r\n--{boundary}--\r\n".encode("ascii")


class UpdateFileView(APIView):
    """POST multipart `file`: update from a signed .lpupdate (servers without internet)."""
    permission_classes = [IsAdmin]

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": tr("system.noFile")}, status=status.HTTP_400_BAD_REQUEST)
        boundary = uuid.uuid4().hex
        try:
            res = _call("POST", "/update/offline", timeout=600, data=_multipart(upload, boundary),
                        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        except UpdaterDown:
            return _down()
        cache.delete(CHECK_KEY)
        return _passthrough(res)


class UpdateProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            return _passthrough(_call("GET", "/update/progress", timeout=5))
        except UpdaterDown:
            return _down()


class BackupsView(APIView):
    """GET: the backups (made before each update, or on request). POST: make one now."""

    def get_permissions(self):
        return [IsAdmin()] if self.request.method == "POST" else [IsAuthenticated()]

    def get(self, request):
        try:
            return _passthrough(_call("GET", "/backups", timeout=10))
        except UpdaterDown:
            return _down()

    def post(self, request):
        try:
            return _passthrough(_call("POST", "/backups", timeout=300))
        except UpdaterDown:
            return _down()


class BackupRestoreView(APIView):
    """POST: bring the data back to a backup (the program version stays)."""
    permission_classes = [IsAdmin]

    def post(self, request, backup_id):
        try:
            return _passthrough(_call("POST", "/rollback", timeout=30, json={"backup_id": backup_id}))
        except UpdaterDown:
            return _down()
