"""Named-seat licensing: seat assignment, releases, hardware binding and the
data gates that depend on them (licensing/seats.py)."""
import datetime
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from label_stations.management.commands.run_discovery import Command as DiscoveryCommand
from label_stations.models import LabelsStations, SeatEvent
from licensing import seats
from licensing.seats import SeatError, SeatPolicy

FINGERPRINT_A = "a" * 32
FINGERPRINT_B = "b" * 32


def policy(limit, can_assign=True):
    return mock.patch(
        "licensing.seats.seat_policy",
        return_value=SeatPolicy(limit=limit, can_assign=can_assign, licensed=True),
    )


def station(name, state=seats.SEAT_ACTIVE, fingerprint=""):
    return LabelsStations.objects.create(
        station_name=name, station_ip=f"192.0.2.{LabelsStations.objects.count() + 10}",
        seat_state=state, station_fingerprint=fingerprint,
    )


class SeatAssignmentTests(TestCase):
    def test_new_station_waits_for_a_seat_when_all_are_taken(self):
        station("Line 1")
        station("Line 2")
        with policy(2):
            self.assertEqual(seats.initial_state(), seats.SEAT_PENDING)
        with policy(3):
            self.assertEqual(seats.initial_state(), seats.SEAT_ACTIVE)
        with policy(None):
            self.assertEqual(seats.initial_state(), seats.SEAT_ACTIVE)

    def test_invalid_licence_never_assigns_new_seats(self):
        with policy(10, can_assign=False):
            self.assertEqual(seats.initial_state(), seats.SEAT_PENDING)
            pending = station("Line 1", state=seats.SEAT_PENDING)
            with self.assertRaises(SeatError):
                seats.activate(pending)

    def test_pending_registrations_are_bounded(self):
        for index in range(seats.MAX_PENDING_STATIONS):
            station(f"Pending {index}", state=seats.SEAT_PENDING)
        with policy(0):
            self.assertIsNone(seats.initial_state())

    def test_activation_needs_a_free_seat(self):
        station("Line 1")
        waiting = station("Line 2", state=seats.SEAT_PENDING)
        with policy(1):
            with self.assertRaises(SeatError) as raised:
                seats.activate(waiting)
            self.assertEqual(raised.exception.code, "station.seatLimitReached")
        with policy(2):
            seats.activate(waiting, actor="admin")
        waiting.refresh_from_db()
        self.assertEqual(waiting.seat_state, seats.SEAT_ACTIVE)
        self.assertTrue(SeatEvent.objects.filter(event="assigned", actor="admin").exists())

    def test_only_the_first_seats_receive_data_when_over_the_cap(self):
        first, second = station("Line 1"), station("Line 2")
        with policy(1):
            self.assertTrue(seats.may_receive_data(first))
            self.assertFalse(seats.may_receive_data(second))
            with self.assertRaises(SeatError) as raised:
                seats.ensure_may_receive_data(second)
            self.assertEqual(raised.exception.code, "station.seatOverLimit")
            summary = seats.summary()
            self.assertTrue(summary["over_limit"])
            self.assertEqual(summary["outside_cap"], 1)
        with policy(None):
            self.assertTrue(seats.may_receive_data(second))

    def test_marking_stations_active_in_the_database_gains_nothing(self):
        holder = station("Line 1")
        extra = [station(f"Copy {index}", state=seats.SEAT_PENDING) for index in range(3)]
        LabelsStations.objects.filter(pk__in=[s.pk for s in extra]).update(seat_state=seats.SEAT_ACTIVE)
        with policy(1):
            fed = [s for s in LabelsStations.objects.all() if seats.may_receive_data(s)]
        self.assertEqual([s.pk for s in fed], [holder.pk])

    def test_seat_order_decides_who_keeps_the_seat(self):
        from django.utils import timezone
        early, late = station("Line 1"), station("Line 2")
        now = timezone.now()
        LabelsStations.objects.filter(pk=late.pk).update(seat_changed_at=now - datetime.timedelta(days=10))
        LabelsStations.objects.filter(pk=early.pk).update(seat_changed_at=now)
        early.refresh_from_db()
        late.refresh_from_db()
        with policy(1):
            self.assertTrue(seats.may_receive_data(late))
            self.assertFalse(seats.may_receive_data(early))


class SeatReleaseTests(TestCase):
    def test_releases_are_rate_limited_per_window(self):
        stations = [station(f"Line {index}") for index in range(4)]
        with policy(2):
            seats.release(stations[0], actor="admin")
            seats.delete(stations[1], actor="admin")
            with self.assertRaises(SeatError) as raised:
                seats.release(stations[2])
            self.assertEqual(raised.exception.code, "station.seatReleaseLimit")
            with self.assertRaises(SeatError):
                seats.delete(stations[3])
        self.assertTrue(LabelsStations.objects.filter(pk=stations[3].pk).exists())
        stations[0].refresh_from_db()
        self.assertEqual(stations[0].seat_state, seats.SEAT_RELEASED)
        self.assertFalse(seats.may_receive_data(stations[0]))

    def test_unlimited_licence_does_not_restrict_releases(self):
        stations = [station(f"Line {index}") for index in range(5)]
        with policy(None):
            for item in stations:
                seats.release(item)
        self.assertEqual(seats.releases_in_window(), 5)

    def test_deleting_a_waiting_station_spends_no_release(self):
        waiting = station("Line 1", state=seats.SEAT_PENDING)
        with policy(2):
            seats.delete(waiting)
        self.assertEqual(seats.releases_in_window(), 0)


class HardwareBindingTests(TestCase):
    def test_first_fingerprint_binds_and_another_device_is_a_conflict(self):
        line = station("Line 1")
        self.assertEqual(seats.observe_fingerprint(line, None, "ping"), seats.FINGERPRINT_LEGACY)
        self.assertEqual(seats.observe_fingerprint(line, FINGERPRINT_A.upper(), "ping"), seats.FINGERPRINT_MATCH)
        self.assertEqual(seats.observe_fingerprint(line, FINGERPRINT_A, "report"), seats.FINGERPRINT_MATCH)
        self.assertEqual(seats.observe_fingerprint(line, FINGERPRINT_B, "discovery"), seats.FINGERPRINT_CONFLICT)
        self.assertEqual(seats.observe_fingerprint(line, FINGERPRINT_B, "discovery"), seats.FINGERPRINT_CONFLICT)
        line.refresh_from_db()
        self.assertEqual(line.station_fingerprint, FINGERPRINT_A)
        self.assertEqual(line.conflict_fingerprint, FINGERPRINT_B)
        self.assertEqual(SeatEvent.objects.filter(event="fingerprint_conflict").count(), 1)

    def test_confirmed_replacement_moves_the_seat_and_spends_a_release(self):
        line = station("Line 1", fingerprint=FINGERPRINT_A)
        seats.observe_fingerprint(line, FINGERPRINT_B, "discovery")
        with policy(2):
            seats.replace_hardware(line, actor="admin")
        line.refresh_from_db()
        self.assertEqual((line.station_fingerprint, line.conflict_fingerprint), (FINGERPRINT_B, ""))
        self.assertEqual(seats.releases_in_window(), 1)
        with policy(2), self.assertRaises(SeatError) as raised:
            seats.replace_hardware(line)
        self.assertEqual(raised.exception.code, "station.noHardwareConflict")


class DiscoveryTests(TestCase):
    def announce(self, station_id, ip, fingerprint=None, name="Station"):
        message = {"type": "LABELPILOT_STATION", "uuid": station_id, "ip": ip, "port": 5556, "name": name}
        if fingerprint:
            message["fingerprint"] = fingerprint
        DiscoveryCommand().handle_station_discovery(message, ip)

    def test_station_over_the_cap_registers_as_pending(self):
        station("Line 1")
        new_id = str(uuid.uuid4())
        with policy(1):
            self.announce(new_id, "192.0.2.50", FINGERPRINT_A)
        created = LabelsStations.objects.get(station_uuid=new_id)
        self.assertEqual(created.seat_state, seats.SEAT_PENDING)
        self.assertFalse(created.is_online)
        self.assertEqual(created.station_fingerprint, FINGERPRINT_A)

    def test_new_station_is_not_merged_into_an_old_dhcp_address(self):
        old = station("Old line")
        new_id = str(uuid.uuid4())
        with policy(None):
            self.announce(new_id, old.station_ip, FINGERPRINT_A)
        self.assertEqual(LabelsStations.objects.count(), 2)
        old.refresh_from_db()
        self.assertEqual(old.station_name, "Old line")

    def test_cloned_identity_never_takes_over_the_station_address(self):
        line = station("Line 1", fingerprint=FINGERPRINT_A)
        original_ip = line.station_ip
        with policy(5):
            self.announce(str(line.station_uuid), "192.0.2.99", FINGERPRINT_B)
        line.refresh_from_db()
        self.assertEqual(line.station_ip, original_ip)
        self.assertEqual(line.conflict_fingerprint, FINGERPRINT_B)


class StationEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_ping_reports_the_seat_and_ignores_a_clone(self):
        line = station("Line 1", fingerprint=FINGERPRINT_A)
        with policy(3):
            response = self.client.get(
                "/api/v1/stations/ping/", {"station_uuid": str(line.station_uuid), "fingerprint": FINGERPRINT_A},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["seat"], {"state": "active", "fingerprint": "match", "used": 1, "limit": 3, "seat_list": None})
        LabelsStations.objects.filter(pk=line.pk).update(is_online=False)
        with policy(3):
            clone = self.client.get(
                "/api/v1/stations/ping/", {"station_uuid": str(line.station_uuid), "fingerprint": FINGERPRINT_B},
            )
        self.assertEqual(clone.json()["seat"]["fingerprint"], "conflict")
        line.refresh_from_db()
        self.assertFalse(line.is_online)

    def test_ping_returns_the_licence_token_only_to_a_bound_active_seat(self):
        line = station("Line 1", fingerprint=FINGERPRINT_A)
        waiting = station("Line 2", state=seats.SEAT_PENDING, fingerprint=FINGERPRINT_B)
        licence = mock.Mock(token="payload.signature")

        def ping(target, fingerprint, **extra):
            with policy(3), \
                    mock.patch("licensing.enforcement.commercial_license_ok", return_value=(True, "ok")), \
                    mock.patch("licensing.core.load_license", return_value=licence):
                return self.client.get("/api/v1/stations/ping/", {
                    "station_uuid": str(target.station_uuid), "fingerprint": fingerprint, **extra,
                }).json()

        self.assertEqual(ping(line, FINGERPRINT_A, license="none")["license_token"], "payload.signature")
        self.assertEqual(ping(line, FINGERPRINT_A, license="refresh")["license_token"], "payload.signature")
        # Only asked for when missing; never to a copy, a waiting seat or a legacy client.
        self.assertNotIn("license_token", ping(line, FINGERPRINT_A))
        self.assertNotIn("license_token", ping(line, FINGERPRINT_B, license="none"))
        self.assertNotIn("license_token", ping(waiting, FINGERPRINT_B, license="none"))
        with mock.patch("licensing.enforcement.commercial_license_ok", return_value=(False, "expired")):
            response = self.client.get("/api/v1/stations/ping/", {
                "station_uuid": str(line.station_uuid), "fingerprint": FINGERPRINT_A, "license": "none",
            }).json()
        self.assertNotIn("license_token", response)

    def test_ping_shows_a_station_beyond_the_cap_as_waiting(self):
        station("Line 1")
        extra = station("Line 2")
        with policy(1):
            response = self.client.get("/api/v1/stations/ping/", {"station_uuid": str(extra.station_uuid)})
        self.assertEqual(response.json()["seat"]["state"], "pending")

    def test_station_data_requires_an_active_seat(self):
        from api.views import _require_station_seat

        waiting = station("Line 1", state=seats.SEAT_PENDING)
        with self.assertRaises(PermissionDenied):
            _require_station_seat(waiting)
        _require_station_seat(station("Line 2"))

    def test_anonymous_hosts_cannot_fetch_station_data_sets(self):
        line = station("Line 1")
        for path in ("download_update", "download_identity"):
            response = self.client.get(f"/api/v1/stations/{line.station_uuid}/{path}/")
            self.assertIn(response.status_code, (401, 403), path)
        response = self.client.get("/api/v1/stations/full_dump/")
        self.assertIn(response.status_code, (401, 403))
        response = self.client.post(f"/api/v1/stations/{line.station_uuid}/sync_data/")
        self.assertIn(response.status_code, (401, 403))

    def test_seat_actions_require_an_administrator(self):
        line = station("Line 1")
        user = get_user_model().objects.create_user("operator", password="x")
        self.client.force_authenticate(user)
        response = self.client.post(f"/api/v1/stations/{line.station_uuid}/release_seat/")
        self.assertEqual(response.status_code, 403)
        admin = get_user_model().objects.create_superuser("chief", password="x")
        self.client.force_authenticate(admin)
        with policy(2):
            response = self.client.post(f"/api/v1/stations/{line.station_uuid}/release_seat/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["seat_state"], "released")
        self.assertEqual(SeatEvent.objects.get(event="released").actor, "chief")

    def test_licence_status_counts_active_seats(self):
        station("Line 1")
        station("Line 2", state=seats.SEAT_PENDING)
        with policy(1):
            data = self.client.get("/api/v1/license/").json()
        self.assertEqual(data["stations_used"], 1)
        self.assertEqual(data["seats"]["pending"], 1)
        self.assertEqual(data["seats"]["limit"], 1)
