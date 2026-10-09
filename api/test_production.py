"""«Сегодня» and a station's page (api/production.py): local days, lines, stops, lists, boxes."""
import datetime
import uuid

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from api.auth_views import ensure_groups
from api.production import day_start, local_today, store_containers
from label_stations.models import LabelsStations
from Nomenclature.models import Nomenclature
from print_jobs.models import PrintJob
from ProductionLogs.models import PrintedContainer, PrintedLabel, ProductionSettings, StationLog


class ProductionTests(TestCase):
    def setUp(self):
        ensure_groups()
        user = User.objects.create_user("chief", password="luna-kora-47")
        user.groups.add(Group.objects.get(name="admin"))
        self.client = APIClient()
        self.client.login(username="chief", password="luna-kora-47")
        self.line = LabelsStations.objects.create(station_name="Линия 1", station_ip="10.0.0.1", station_port=5000,
                                                  station_uuid=uuid.uuid4(), is_online=True)
        self.ham = Nomenclature.objects.create(name="Ветчина", article="1", exp_date=10, close_box_counter=10)
        self.today = day_start(local_today())
        self.n = 0

    def label(self, at, operator="Иванова", deleted_at=None, product=None, grams=400.0, **extra):
        self.n += 1
        return PrintedLabel.objects.create(
            station=self.line, product=product or self.ham, product_name_snapshot=(product or self.ham).name,
            unique_id=f"u-{self.n}", printed_at=at, station_user_name=operator, weight_netto_grams=grams,
            is_deleted=deleted_at is not None, deleted_at=deleted_at, **extra)

    def at(self, hours, minutes=0, days=0):
        return self.today + datetime.timedelta(days=days, hours=hours, minutes=minutes)

    def get(self, url, **params):
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response

    def test_today_counts_local_hours_and_the_same_hour_yesterday(self):
        now_hour = timezone.now().astimezone().hour
        self.label(self.at(0, 5))
        self.label(self.at(0, 6), deleted_at=self.at(0, 7))
        self.label(self.at(0, 5, days=-1))
        late_yesterday = self.at(23, 59, days=-1)
        self.label(late_yesterday)
        body = self.get("/api/v1/production/today/").json()
        self.assertEqual(body["totals"]["labels"], 1)
        self.assertEqual(body["totals"]["deleted"], 1)
        self.assertEqual(body["hourly"][0], 1)
        # 00:05 yesterday is before this hour of yesterday; 23:59 only once the day is that late.
        self.assertEqual(body["totals"]["yesterday_same_time"], 1 if now_hour < 23 else 2)
        line = body["stations"][0]
        self.assertEqual((line["name"], line["labels"], line["kg"], line["operator"]), ("Линия 1", 1, 0.4, "Иванова"))

    def test_a_line_shows_its_job_with_an_eta_and_its_open_fault_until_the_next_label(self):
        now = timezone.now()
        for minutes in (50, 40, 30, 20):
            self.label(now - datetime.timedelta(minutes=minutes))
        PrintJob.objects.create(station=self.line, nomenclature=self.ham, quantity=10, printed_qty=6, marking_date=local_today(),
                                status="sent", sent_at=now)
        StationLog.objects.create(station=self.line, level="ERROR", component="printer", message="Принтер: нет бумаги",
                                  timestamp=now - datetime.timedelta(minutes=10))
        line = self.get("/api/v1/production/today/").json()["stations"][0]
        self.assertEqual(line["rate"], 4)
        self.assertEqual((line["job"]["printed"], line["job"]["quantity"], line["job"]["eta_minutes"]), (6, 10, 60))
        self.assertEqual(line["fault"]["message"], "Принтер: нет бумаги")
        StationLog.objects.create(station=self.line, level="INFO", component="printer", message="Принтер: снова готов к печати",
                                  timestamp=now - datetime.timedelta(minutes=5))
        line = self.get("/api/v1/production/today/").json()["stations"][0]
        self.assertIsNone(line["fault"], "the station's all-clear ends the fault")
        StationLog.objects.filter(level="INFO").delete()
        self.label(now - datetime.timedelta(minutes=1))
        line = self.get("/api/v1/production/today/").json()["stations"][0]
        self.assertIsNone(line["fault"])

    def test_a_day_of_a_station_has_hours_products_operators_and_stops(self):
        day = local_today() - datetime.timedelta(days=1)
        base = day_start(day)
        for minutes in (0, 2, 4, 30, 32, 60):  # stops 04→30 (printer error) and 32→60 (idle)
            self.label(base + datetime.timedelta(hours=8, minutes=minutes), operator="Петров" if minutes >= 30 else "Иванова")
        StationLog.objects.create(station=self.line, level="ERROR", component="printer", message="Принтер: нет бумаги",
                                  timestamp=base + datetime.timedelta(hours=8, minutes=10))
        url = f"/api/v1/stations/{self.line.station_uuid}/stats/"
        hidden = self.get(url, **{"from": day.isoformat()}).json()
        self.assertEqual((hidden["operators"], hidden["operator_output"]), ([], False))  # off until an admin enables it
        self.assertEqual(self.client.put("/api/v1/production/settings/", {"operator_output": True}, format="json").status_code, 200)
        body = self.get(url, **{"from": day.isoformat()}).json()
        self.assertTrue(body["single_day"])
        self.assertEqual(body["series"][8]["count"], 5)
        self.assertEqual(body["series"][9]["count"], 1)
        self.assertEqual(body["totals"]["labels"], 6)
        self.assertEqual(body["totals"]["avg_kg"], 0.4)
        self.assertEqual([(o["name"], o["pcs"]) for o in body["operators"]], [("Иванова", 3), ("Петров", 3)])
        self.assertEqual([(s["kind"], s["minutes"]) for s in body["work"]["stops"]], [("fault", 26), ("idle", 28)])
        self.assertEqual(body["work"]["stops"][0]["reason"], "Принтер: нет бумаги")

    def test_today_a_standing_line_shows_its_fault_and_the_stop_up_to_now(self):
        now = timezone.now()
        if now.astimezone().hour < 2:
            self.skipTest("the labels an hour ago would fall on yesterday")
        for minutes in (60, 58, 56):
            self.label(now - datetime.timedelta(minutes=minutes))
        StationLog.objects.create(station=self.line, level="ERROR", component="printer", message="Принтер: нет бумаги",
                                  timestamp=now - datetime.timedelta(minutes=50))
        body = self.get(f"/api/v1/stations/{self.line.station_uuid}/stats/").json()
        self.assertEqual(body["fault"]["message"], "Принтер: нет бумаги")
        stop = body["work"]["stops"][-1]
        self.assertEqual((stop["kind"], stop["ongoing"], stop["reason"]), ("fault", True, "Принтер: нет бумаги"))
        self.assertIsNotNone(body["work"]["until"])
        self.assertEqual(body["work"]["minutes"], 4)  # 60→56 printing; the stop since is not work

    def test_a_period_is_counted_per_day_and_compared_with_the_period_before(self):
        today = local_today()
        self.label(self.at(9))
        self.label(self.at(9, days=-1))
        self.label(self.at(9, days=-3))  # the previous 2-day period
        body = self.get(f"/api/v1/stations/{self.line.station_uuid}/stats/",
                        **{"from": (today - datetime.timedelta(days=1)).isoformat(), "to": today.isoformat()}).json()
        self.assertFalse(body["single_day"])
        self.assertEqual([p["count"] for p in body["series"]], [1, 1])
        self.assertEqual(body["totals"]["previous_labels"], 1)
        days = self.get(f"/api/v1/stations/{self.line.station_uuid}/days/", month=today.isoformat()[:7]).json()["days"]
        self.assertIn(today.isoformat(), days)

    def test_the_label_list_searches_filters_deleted_and_exports_csv(self):
        self.label(self.at(1), batch="П-1", box_number="К-0288")
        self.label(self.at(2), deleted_at=self.at(3), batch="П-2")
        url = f"/api/v1/stations/{self.line.station_uuid}/labels/"
        body = self.get(url).json()
        self.assertEqual((body["counts"]["pack"], body["total"], body["deleted"]), (1, 2, 1))
        self.assertEqual(self.get(url, q="К-0288").json()["rows"][0]["box"], "К-0288")
        only = self.get(url, deleted="1").json()["rows"]
        self.assertEqual([r["batch"] for r in only], ["П-2"])
        csv = self.client.get(url, {"export": "csv"})
        self.assertEqual(csv["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Партия", csv.content.decode("utf-8-sig").splitlines()[0])
        self.assertIn("filename*=utf-8''%D0%9B%D0%B8%D0%BD%D0%B8%D1%8F_1_pack_", csv["Content-Disposition"])

    def test_boxes_are_upserted_from_reports_open_then_closed(self):
        opened = self.at(1).isoformat()
        box = {"unique_id": "s-box-1", "number": "К-0288", "product_id": self.ham.id, "packs": 6, "capacity": 10,
               "opened_at": opened, "weight_netto_grams": 2400.0, "pallet_number": "П-003"}
        store_containers(self.line, {"boxes": [box]})
        store_containers(self.line, {"boxes": [{**box, "packs": 10, "closed_at": self.at(2).isoformat()}]})
        stored = PrintedContainer.objects.get(unique_id="s-box-1")
        self.assertEqual((stored.packs_count, stored.is_closed, stored.parent_number, stored.product_name_snapshot),
                         (10, True, "П-003", "Ветчина"))
        rows = self.get(f"/api/v1/stations/{self.line.station_uuid}/labels/", level="box").json()["rows"]
        self.assertEqual((rows[0]["number"], rows[0]["packs"], rows[0]["closed"]), ("К-0288", 10, True))

    def test_only_an_admin_turns_on_output_per_operator(self):
        manager = User.objects.create_user("shift", password="luna-kora-47")
        manager.groups.add(Group.objects.get(name="manager"))
        client = APIClient()
        client.force_authenticate(manager)
        self.assertEqual(client.get("/api/v1/production/settings/").json(), {"operator_output": False})
        self.assertEqual(client.put("/api/v1/production/settings/", {"operator_output": True}, format="json").status_code, 403)
        self.assertFalse(ProductionSettings.current().operator_output)

    def test_production_data_needs_a_signed_in_user(self):
        anonymous = APIClient()
        for url in ("/api/v1/production/today/", "/api/v1/production/settings/", f"/api/v1/stations/{self.line.station_uuid}/stats/",
                    f"/api/v1/stations/{self.line.station_uuid}/labels/", "/api/v1/statistics/",
                    "/api/v1/statistics/station_labels/"):
            self.assertIn(anonymous.get(url).status_code, (401, 403), url)
