"""Print job list filters and completing a job by hand."""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from label_stations.models import LabelsStations
from Nomenclature.models import Nomenclature

from .models import PrintJob


class PrintJobListTests(TestCase):
    url = "/api/v1/print_jobs/"

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user("manager", password="x"))
        station = LabelsStations.objects.create(station_name="Line 1", station_ip="192.0.2.10")
        product = Nomenclature.objects.create(name="Ham", article="A1", exp_date=10, close_box_counter=10)
        self.make = lambda **fields: PrintJob.objects.create(
            station=station, nomenclature=product, quantity=10, marking_date=datetime.date.today(), **fields)

    def ids(self, **params):
        return sorted(row["id"] for row in self.client.get(self.url, params).json())

    def test_status_filter(self):
        failed = self.make(status="error")
        waiting = self.make(status="pending")
        self.make(status="sent")
        self.assertEqual(self.ids(status="error"), [failed.pk])
        self.assertEqual(self.ids(status="error,pending"), sorted([failed.pk, waiting.pk]))

    def test_recent_days_drops_only_old_completed_jobs(self):
        old_sent = self.make(status="sent")
        recent_done = self.make(status="completed", completed_at=timezone.now() - datetime.timedelta(days=2))
        old_done = self.make(status="completed", completed_at=timezone.now() - datetime.timedelta(days=40))
        # Completed by an older server, before completed_at existed: its last change counts.
        legacy_done = self.make(status="completed")
        PrintJob.objects.filter(pk__in=[old_sent.pk, legacy_done.pk]).update(
            updated_at=timezone.now() - datetime.timedelta(days=40))

        self.assertEqual(self.ids(recent_days="30"), sorted([old_sent.pk, recent_done.pk]))
        self.assertEqual(len(self.ids()), 4)
        self.assertIn(old_done.pk, self.ids())

    def test_marking_done_by_hand_sets_the_time(self):
        job = self.make(status="sent")
        self.client.patch(f"{self.url}{job.pk}/", {"status": "completed"}, format="json")
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")
        self.assertIsNotNone(job.completed_at)
