"""Statistics endpoints built on printed labels."""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from label_stations.models import LabelsStations
from ProductionLogs.models import PrintedLabel


def label(station, printed_at, grams, product, deleted=False):
    return PrintedLabel.objects.create(
        station=station, printed_at=printed_at, weight_netto_grams=grams,
        product_name_snapshot=product, is_deleted=deleted,
        unique_id=f"L-{PrintedLabel.objects.count() + 1}",
    )


class StationsTodayTests(TestCase):
    url = "/api/v1/statistics/stations_today/"

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user("manager", password="x"))
        self.now = timezone.now()
        self.midnight = self.now.replace(hour=0, minute=0, second=0, microsecond=0)

    def test_counts_good_labels_since_midnight_per_station(self):
        line = LabelsStations.objects.create(station_name="Line 1", station_ip="192.0.2.10")
        LabelsStations.objects.create(station_name="Idle", station_ip="192.0.2.11")
        label(line, self.midnight + datetime.timedelta(seconds=1), 500, "Ham")
        label(line, self.now, 250, "Salami")
        label(line, self.now, 900, "Deleted", deleted=True)
        label(line, self.midnight - datetime.timedelta(minutes=5), 700, "Yesterday")

        data = self.client.get(self.url).json()

        self.assertEqual(data["date"], self.midnight.date().isoformat())
        self.assertEqual(len(data["hours"]), self.now.hour + 1)
        self.assertEqual(len(data["stations"]), 1)
        row = data["stations"][0]
        self.assertEqual(row["id"], line.pk)
        self.assertEqual(row["labels"], 2)
        self.assertEqual(row["weight_kg"], 0.75)
        self.assertEqual(row["last_product"], "Salami")
        self.assertEqual(sum(row["hourly"]), 2)
        self.assertEqual(row["hourly"][0], 1 if self.now.hour else 2)

    def test_requires_a_signed_in_user(self):
        response = APIClient().get(self.url)
        self.assertIn(response.status_code, (401, 403))


class TopProductsTodayTests(TestCase):
    def test_counts_only_todays_good_labels(self):
        now = timezone.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        line = LabelsStations.objects.create(station_name="Line 1", station_ip="192.0.2.10")
        label(line, now, 100, "Ham")
        label(line, now, 100, "Ham")
        label(line, now, 100, "Salami")
        label(line, now, 100, "Salami", deleted=True)
        for _ in range(3):
            label(line, midnight - datetime.timedelta(minutes=5), 100, "Yesterday")

        client = APIClient()
        # The dashboard statistics are for signed-in users only.
        client.force_authenticate(get_user_model().objects.create_user("viewer", password="luna-kora-47"))
        data = client.get("/api/v1/statistics/").json()

        self.assertEqual(data["top_products_today"], [{"name": "Ham", "count": 2}, {"name": "Salami", "count": 1}])
        self.assertEqual(data["top_products"][0], {"name": "Yesterday", "count": 3})
