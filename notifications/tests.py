"""Notification service, periodic checks, the API and the events that the station
endpoints raise (report errors, job progress, heartbeat, sends)."""
import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from label_stations.models import LabelsStations
from licensing import seats
from licensing.seats import SeatPolicy
from Nomenclature.models import Nomenclature
from print_jobs.models import PrintJob
from ProductionLogs.models import StationLog

from . import checks
from .models import Notification
from .service import ensure_notification, raise_notification, resolve
from .versions import is_newer


def policy(limit):
    return mock.patch("licensing.seats.seat_policy", return_value=SeatPolicy(limit=limit, can_assign=True, licensed=True))


def make_station(name="Line 1", **fields):
    return LabelsStations.objects.create(station_name=name, station_ip=f"192.0.2.{LabelsStations.objects.count() + 10}", **fields)


class ServiceTests(TestCase):
    def test_repeat_counts_and_reopen_after_resolve(self):
        first = raise_notification("k", "station.error", "error", {"a": 1})
        again = raise_notification("k", "station.error", "error", {"a": 2})
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(again.count, 2)
        self.assertEqual(again.params, {"a": 2})

        resolve("k")
        reopened = raise_notification("k", "station.error", "error")
        self.assertEqual(reopened.pk, first.pk)
        self.assertIsNone(reopened.resolved_at)
        self.assertEqual(reopened.count, 1)

    def test_ensure_does_not_bump_an_open_condition(self):
        a = ensure_notification("s", "station.offline", "error", {"since": "x"})
        b = ensure_notification("s", "station.offline", "error", {"since": "x"})
        self.assertEqual((a.pk, Notification.objects.get(pk=a.pk).count), (b.pk, 1))

    def test_version_compare(self):
        self.assertTrue(is_newer("1.1.35", "1.1.34-qa"))
        self.assertFalse(is_newer("2.0.6", "2.0.6"))
        self.assertFalse(is_newer("", "1.0"))


class StationCheckTests(TestCase):
    def test_offline_after_ten_minutes_and_resolved_when_back(self):
        line = make_station(is_online=False)
        now = timezone.now()
        LabelsStations.objects.filter(pk=line.pk).update(changed_at=now - datetime.timedelta(minutes=9))
        with policy(5):
            checks.check_stations(now)
        self.assertFalse(Notification.objects.filter(code="station.offline").exists())

        LabelsStations.objects.filter(pk=line.pk).update(changed_at=now - datetime.timedelta(minutes=11))
        with policy(5):
            checks.check_stations(now)
        row = Notification.objects.get(code="station.offline")
        self.assertEqual((row.severity, row.link_tab, row.link_id), ("error", "stations", str(line.station_uuid)))

        LabelsStations.objects.filter(pk=line.pk).update(is_online=True)
        with policy(5):
            checks.check_stations(now)
        row.refresh_from_db()
        self.assertIsNotNone(row.resolved_at)

    def test_conflict_is_not_also_reported_as_offline(self):
        line = make_station(is_online=False, conflict_fingerprint="b" * 32)
        now = timezone.now()
        LabelsStations.objects.filter(pk=line.pk).update(changed_at=now - datetime.timedelta(minutes=30))
        with policy(5):
            checks.check_stations(now)
        self.assertEqual(list(Notification.objects.values_list("code", flat=True)), ["station.conflict"])

    def test_conflict_is_critical_and_released_station_is_quiet(self):
        line = make_station(is_online=True, conflict_fingerprint="b" * 32)
        pending = make_station("Line 2", is_online=True, seat_state=seats.SEAT_PENDING)
        with policy(5):
            checks.check_stations()
        self.assertEqual(Notification.objects.get(code="station.conflict").severity, "critical")
        self.assertEqual(Notification.objects.get(code="station.pending").severity, "warning")

        LabelsStations.objects.filter(pk=pending.pk).update(seat_state=seats.SEAT_RELEASED, is_online=False)
        LabelsStations.objects.filter(pk=line.pk).update(conflict_fingerprint="")
        with policy(5):
            checks.check_stations()
        self.assertFalse(Notification.objects.filter(resolved_at__isnull=True).exists())

    def test_server_update_from_the_local_updater(self):
        with self.settings(VERSION="1.1.34"):
            checks.check_server_update(fetch=lambda: {"available": True, "version": "1.1.35"})
            self.assertEqual(Notification.objects.get(code="update.server").params, {"version": "1.1.35"})
            checks.check_server_update(fetch=lambda: {"available": False})
        self.assertIsNotNone(Notification.objects.get(code="update.server").resolved_at)


class ApiTests(TestCase):
    url = "/api/v1/notifications/"

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user("manager", password="x")
        self.client.force_authenticate(self.user)

    def test_requires_a_signed_in_user(self):
        self.assertIn(APIClient().get(self.url).status_code, (401, 403))

    def test_unread_counts_toasts_and_seen(self):
        before = timezone.now() - datetime.timedelta(seconds=1)
        raise_notification("a", "station.conflict", "critical")
        raise_notification("b", "station.pending", "warning")
        raise_notification("c", "job.completed", "info")

        data = self.client.get(self.url, {"since": before.isoformat()}).json()
        self.assertEqual(data["unread"], {"critical": 1, "error": 0, "warning": 1, "total": 2})
        self.assertEqual([t["code"] for t in data["toasts"]], ["station.conflict"])
        self.assertEqual(data["items"][0]["code"], "station.conflict")

        self.client.post(self.url + "seen/")
        self.assertEqual(self.client.get(self.url).json()["unread"]["total"], 0)
        # A repeat after the user looked makes it unread again (Windows clocks are coarse).
        raise_notification("a", "station.conflict", "critical", now=timezone.now() + datetime.timedelta(seconds=1))
        self.assertEqual(self.client.get(self.url).json()["unread"]["critical"], 1)


class StationEventTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.line = make_station(is_online=True, station_fingerprint="a" * 32)
        product = Nomenclature.objects.create(name="Ham", article="A1", exp_date=10, close_box_counter=10)
        self.job = PrintJob.objects.create(station=self.line, nomenclature=product, quantity=10, marking_date=datetime.date.today(), status="sent")

    def upload(self, payload):
        with mock.patch("common.crypto_utils.decrypt_data", return_value=payload):
            return self.client.post("/api/v1/stations/upload_report/", {"file": SimpleUploadedFile("r.lpr", b"x")})

    def test_report_errors_progress_and_completion(self):
        payload = {
            "station_uuid": str(self.line.station_uuid),
            "logs": [
                {"event_uid": "e1", "level": "ERROR", "component": "printer", "message": "Нет бумаги", "timestamp": timezone.now().isoformat()},
                {"event_uid": "e2", "level": "INFO", "component": "print", "message": "ok", "timestamp": timezone.now().isoformat()},
            ],
            "print_jobs": [{"job_id": self.job.pk, "printed_qty": 4, "status": "in_progress"}],
        }
        self.assertEqual(self.upload(payload).status_code, 200)
        error = Notification.objects.get(code="station.error")
        self.assertEqual((error.params["component"], error.params["message"]), ("printer", "Нет бумаги"))
        self.assertEqual(StationLog.objects.get(event_uid="e1").component, "printer")
        self.job.refresh_from_db()
        self.assertEqual((self.job.printed_qty, self.job.status), (4, "sent"))

        # A retry of the same report changes nothing; completion is a quiet info event.
        payload["print_jobs"] = [{"job_id": self.job.pk, "printed_qty": 10, "status": "completed"}]
        self.upload(payload)
        error.refresh_from_db()
        self.assertEqual(error.count, 1)
        self.job.refresh_from_db()
        self.assertEqual((self.job.printed_qty, self.job.status), (10, "completed"))
        self.assertEqual(Notification.objects.get(code="job.completed").severity, "info")

    def test_pushed_reports_stay_out_of_the_activity_list_and_never_link_a_tare(self):
        from Packs.models import Pack
        from ProductionLogs.models import PrintedLabel
        from server_activity.models import ServerEvent
        tare = Pack.objects.create(name="Лоток 0,5 кг")
        label = {"unique_id": f"{self.line.station_uuid}-pack-{tare.pk}", "station_pack_id": tare.pk,
                 "pack_id": tare.pk, "pack_name": "000017", "product_id": self.job.nomenclature_id,
                 "printed_at": timezone.now().isoformat()}
        self.upload({"station_uuid": str(self.line.station_uuid), "printed_labels": [label]})
        stored = PrintedLabel.objects.get(unique_id=label["unique_id"])
        # The station's own pack row id is not a tare id, even when the numbers match.
        self.assertIsNone(stored.pack)
        self.assertEqual(stored.pack_name_snapshot, "000017")
        self.assertFalse(ServerEvent.objects.filter(action="report_imported").exists())

        # A report an admin uploads by hand (.lpr from USB) is listed.
        admin = get_user_model().objects.create_superuser("chief", password="x")
        self.client.force_authenticate(admin)
        self.upload({"station_uuid": str(self.line.station_uuid), "printed_labels": [dict(label, unique_id="other-1")]})
        self.assertEqual(ServerEvent.objects.filter(action="report_imported").count(), 1)

    def test_rejected_report_is_critical(self):
        with mock.patch("common.crypto_utils.decrypt_data", side_effect=ValueError("bad")):
            response = self.client.post("/api/v1/stations/upload_report/", {"file": SimpleUploadedFile("r.lpr", b"x")})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Notification.objects.get(code="station.report_invalid").severity, "critical")

    def test_outdated_client_from_report(self):
        with self.settings(MIN_CLIENT_VERSION="2.0.0", LATEST_CLIENT_VERSION="2.0.7"):
            self.upload({"station_uuid": str(self.line.station_uuid), "client_version": "1.9.0"})
        self.assertEqual(Notification.objects.get(code="station.client_outdated").severity, "error")
        self.assertEqual(Notification.objects.get(code="update.client").params, {"version": "2.0.7"})

    def test_heartbeat_ends_offline(self):
        ensure_notification(f"station:{self.line.station_uuid}:offline", "station.offline", "error")
        with policy(5):
            self.client.get("/api/v1/stations/ping/", {"station_uuid": str(self.line.station_uuid), "fingerprint": "a" * 32})
        self.assertIsNotNone(Notification.objects.get(code="station.offline").resolved_at)

    def test_failed_send_raises_and_success_resolves(self):
        import requests

        admin = get_user_model().objects.create_superuser("chief", password="x")
        self.client.force_authenticate(admin)
        self.job.status = "pending"
        self.job.save()
        with mock.patch("api.views._require_license_for_export"), mock.patch("api.views._require_station_seat"), \
                mock.patch("api.views.requests.post", side_effect=requests.ConnectionError("refused")), \
                mock.patch("common.crypto_utils.encrypt_data", return_value=b"x"):
            self.client.post(f"/api/v1/print_jobs/{self.job.pk}/send_to_station/")
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "error")
        self.assertIn("refused", self.job.last_error)
        self.assertIsNone(Notification.objects.get(code="job.send_failed").resolved_at)

        ok = mock.Mock()
        ok.raise_for_status.return_value = None
        with mock.patch("api.views._require_license_for_export"), mock.patch("api.views._require_station_seat"), \
                mock.patch("api.views.requests.post", return_value=ok), \
                mock.patch("common.crypto_utils.encrypt_data", return_value=b"x"):
            self.client.post(f"/api/v1/print_jobs/{self.job.pk}/send_to_station/")
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.last_error), ("sent", ""))
        self.assertIsNotNone(self.job.sent_at)
        self.assertIsNotNone(Notification.objects.get(code="job.send_failed").resolved_at)
