"""Subscription grace, the trusted licence clock, licence refresh and the
vendor-signed seat list (licensing/core.py, clock.py, refresh.py, seat_list.py)."""
import contextlib
import datetime
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from licensing import clock, core, refresh, seat_list
from licensing.core import b64url_encode
from licensing.native_guard import NativeGuardResult

MACHINE = "a" * 32
VENDOR_KEY = Ed25519PrivateKey.generate()
VENDOR_PUBLIC_HEX = VENDOR_KEY.public_key().public_bytes(
    serialization.Encoding.Raw, serialization.PublicFormat.Raw,
).hex()


def signed(key=VENDOR_KEY, **overrides):
    payload = {
        "customer": "Muster Fleischwaren GmbH", "edition": "Subscription", "expires": "2026-12-31",
        "features": [], "issued": "2026-01-01", "key_version": 1, "license_id": "LP-TEST-0001",
        "machine_id": MACHINE, "max_stations": 3,
    }
    payload.update(overrides)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return b64url_encode(raw) + "." + b64url_encode(key.sign(raw))


class LicenceTestCase(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.license_path = self.root / "license.lpl"
        self.mark_path = self.root / "license-clock.json"
        for patcher in (
            mock.patch.object(core, "LICENSE_PUBLIC_KEY_HEX", VENDOR_PUBLIC_HEX),
            mock.patch.object(core, "_license_path", return_value=self.license_path),
            mock.patch.object(core, "machine_id", return_value=MACHINE),
            mock.patch.dict(os.environ, {
                "LABELPILOT_LICENSE_CLOCK_PATH": str(self.mark_path),
                "LICENSE_TELEMETRY": "0",
                "LICENSE_REFRESH": "1",
            }),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        core._cached_state = None
        clock.reset_cache()
        self.addCleanup(clock.reset_cache)

    def install(self, **overrides):
        refresh.install_license_token(signed(**overrides))
        core._cached_state = None

    @contextlib.contextmanager
    def on(self, day):
        """The OS clock reads `day` (noon UTC); the trusted clock is re-read."""
        moment = datetime.datetime.fromisoformat(f"{day}T12:00:00+00:00")
        clock.reset_cache()
        with mock.patch.object(clock, "_utcnow", return_value=moment):
            yield
        clock.reset_cache()

    def commercial(self):
        from licensing.enforcement import commercial_license_ok
        native = NativeGuardResult(available=True, ok=True, reason="ok")
        with mock.patch("licensing.native_guard.verify_license_native", return_value=native), \
                mock.patch("licensing.integrity.integrity_ok", return_value=True):
            return commercial_license_ok()


class GraceTests(LicenceTestCase):
    def test_an_expired_subscription_keeps_working_for_fourteen_days(self):
        from licensing.seats import seat_policy

        self.install(expires="2026-12-31")
        with self.on("2026-12-31"):
            self.assertFalse(core.license_state().expired)
            self.assertEqual(core.license_status()["days_left"], 0)
        with self.on("2027-01-05"):
            state = core.license_state()
            self.assertTrue(state.expired and state.in_grace and not state.past_grace)
            status = core.license_status()
            self.assertEqual((status["grace"], status["grace_until"], status["days_left"]), (True, "2027-01-14", 9))
            self.assertTrue(seat_policy().can_assign)
            self.assertEqual(self.commercial(), (True, "ok"))
        with self.on("2027-01-15"):
            self.assertTrue(core.license_state().past_grace)
            self.assertFalse(core.license_status()["grace"])
            self.assertFalse(seat_policy().can_assign)
            self.assertEqual(self.commercial(), (False, "expired"))

    def test_a_lifetime_licence_never_expires(self):
        self.install(expires=None)
        with self.on("2099-01-01"):
            status = core.license_status()
            self.assertFalse(status["expired"] or status["grace"])
            self.assertIsNone(status["grace_until"])
            self.assertIsNone(status["days_left"])

    def test_expiry_is_not_cached_with_the_parsed_file(self):
        self.install(expires="2026-12-31")
        with self.on("2026-12-30"):
            self.assertFalse(core.license_state().expired)
        with self.on("2027-03-01"):
            self.assertTrue(core.license_state().past_grace)


class ClockTests(LicenceTestCase):
    def test_turning_the_clock_back_gains_nothing(self):
        self.install(expires="2026-12-31")
        with self.on("2027-02-01"):
            self.assertTrue(core.license_state().past_grace)
        with self.on("2026-12-01"):
            state = core.license_state()
            self.assertTrue(state.clock_rollback)
            self.assertTrue(state.past_grace)
            self.assertEqual(state.today, datetime.date(2027, 2, 1))
            self.assertTrue(core.license_status()["clock_rollback"])

    def test_small_clock_corrections_are_not_a_rollback(self):
        self.install(expires="2026-12-31")
        with self.on("2026-12-10"):
            core.license_state()
        moment = datetime.datetime(2026, 12, 9, 20, 0, tzinfo=datetime.timezone.utc)
        clock.reset_cache()
        with mock.patch.object(clock, "_utcnow", return_value=moment):
            self.assertFalse(core.license_state().clock_rollback)

    def test_deleting_the_mark_falls_back_to_server_timestamps(self):
        from server_activity.models import ServerEvent

        self.install(expires="2026-12-31")
        event = ServerEvent.objects.create(action="other", description="received")
        ServerEvent.objects.filter(pk=event.pk).update(
            created_at=datetime.datetime(2027, 2, 1, 9, 0, tzinfo=datetime.timezone.utc),
        )
        self.mark_path.unlink(missing_ok=True)
        with self.on("2026-12-01"):
            state = core.license_state()
            self.assertTrue(state.clock_rollback)
            self.assertTrue(state.past_grace)

    def test_an_edited_mark_does_not_verify(self):
        self.install(expires="2026-12-31")
        with self.on("2027-02-01"):
            core.license_state()
        data = json.loads(self.mark_path.read_text(encoding="utf-8"))
        data["mark"] = "2026-11-01T00:00:00+00:00"
        self.mark_path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIsNone(clock._read_mark())

    def test_a_vendor_reissue_rebases_a_mark_pushed_into_the_future(self):
        self.install(expires="2026-12-31")
        with self.on("2030-01-01"):  # the clock was once set years ahead
            core.license_state()
        with self.on("2026-12-01"):
            self.assertTrue(core.license_state().past_grace)
        self.install(issued="2026-11-30", expires="2027-12-31")
        with self.on("2026-12-01"):
            state = core.license_state()
            self.assertFalse(state.clock_rollback)
            self.assertFalse(state.expired)

    def test_the_signed_issue_date_is_a_floor(self):
        self.install(issued="2026-06-01", expires="2026-06-30")
        with self.on("2026-01-01"):
            state = core.license_state()
            self.assertTrue(state.clock_rollback)
            self.assertEqual(state.today, datetime.date(2026, 6, 1))
            self.assertFalse(state.expired)


class GuardAuthenticityTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.guard = Path(directory.name) / "labelpilot-license-guard.exe"
        self.guard.write_bytes(b"genuine guard")

    def signed(self, record, strict=True):
        from licensing import native_guard
        return mock.patch.multiple(
            "licensing.integrity", signed_guard_record=mock.Mock(return_value=record),
        ), mock.patch.object(native_guard, "_strict_mode", return_value=strict)

    def test_only_the_signed_guard_binary_is_trusted(self):
        import hashlib
        from licensing import native_guard
        genuine = {"sha256": hashlib.sha256(b"genuine guard").hexdigest(), "size": len(b"genuine guard")}
        patches = self.signed(genuine)
        with patches[0], patches[1]:
            self.assertTrue(native_guard._guard_is_signed(self.guard))
            self.guard.write_bytes(b'@echo {"ok": true}')
            self.assertFalse(native_guard._guard_is_signed(self.guard))

    def test_a_forged_release_manifest_rejects_the_guard(self):
        from licensing import native_guard
        from licensing.integrity import IntegrityError
        with mock.patch("licensing.integrity.signed_guard_record", side_effect=IntegrityError("forged")):
            self.assertFalse(native_guard._guard_is_signed(self.guard))

    def test_a_source_tree_needs_a_release_manifest_only_in_production(self):
        from licensing import native_guard
        for strict, expected in ((True, False), (False, True)):
            patches = self.signed(None, strict=strict)
            with patches[0], patches[1]:
                self.assertEqual(native_guard._guard_is_signed(self.guard), expected)


class RefreshTests(LicenceTestCase):
    def answer(self, status="ok", token=None, error=None):
        if error is not None:
            return mock.patch.object(refresh, "_fetch_token", side_effect=error)
        return mock.patch.object(refresh, "_fetch_token", return_value=(status, token))

    def test_a_renewal_is_installed(self):
        self.install(expires="2026-12-31")
        renewed = signed(issued="2026-12-20", expires="2027-12-31", max_stations=5)
        with self.on("2026-12-21"), self.answer(token=renewed):
            result = refresh.refresh_license()
            self.assertEqual(result, refresh.RefreshResult(refresh.UPDATED, "2027-12-31"))
            core._cached_state = None
            status = core.license_status()
        self.assertEqual((status["expires"], status["max_stations"]), ("2027-12-31", 5))
        self.assertEqual(self.license_path.read_text(encoding="utf-8"), renewed)

    def test_tokens_that_must_not_replace_the_licence(self):
        self.install(issued="2026-06-01", expires="2026-12-31")
        original = self.license_path.read_text(encoding="utf-8")
        attacker = Ed25519PrivateKey.generate()
        cases = [
            (signed(issued="2026-06-01", expires="2026-12-31"), refresh.CURRENT),
            (signed(license_id="LP-OTHER-0002", issued="2026-07-01"), refresh.REJECTED),
            (signed(machine_id="b" * 32, issued="2026-07-01"), refresh.REJECTED),
            (signed(key_version=2, issued="2026-07-01"), refresh.REJECTED),
            (signed(issued="2026-05-01", expires="2027-12-31"), refresh.CURRENT),
            (signed(attacker, issued="2026-07-01", expires="2030-12-31"), refresh.REJECTED),
        ]
        for token, expected in cases:
            with self.answer(token=token):
                self.assertEqual(refresh.refresh_license().status, expected, token)
            self.assertEqual(self.license_path.read_text(encoding="utf-8"), original)

    def test_offline_unknown_and_disabled(self):
        with self.answer(token="x"):
            self.assertEqual(refresh.refresh_license().status, refresh.NO_LICENSE)
        self.install()
        with self.answer(error=OSError("offline")):
            self.assertEqual(refresh.refresh_license().status, refresh.UNAVAILABLE)
        with self.answer(status="not_found"):
            self.assertEqual(refresh.refresh_license().status, refresh.NOT_FOUND)
        with mock.patch.dict(os.environ, {"LICENSE_REFRESH": "0"}), self.answer(token="x"):
            self.assertEqual(refresh.refresh_license().status, refresh.DISABLED)

    def test_refresh_endpoint_is_for_administrators(self):
        self.install()
        client = APIClient()
        self.assertIn(client.post("/api/v1/license/refresh/").status_code, (401, 403))
        client.force_authenticate(get_user_model().objects.create_superuser("chief", password="x"))
        with self.answer(status="not_found"):
            response = client.post("/api/v1/license/refresh/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["refresh"]["status"], refresh.NOT_FOUND)
        self.assertEqual(response.json()["license_id"], "LP-TEST-0001")


FIXTURE = json.loads((Path(__file__).resolve().parent / "fixtures" / "seat-list-contract.json").read_text(encoding="utf-8"))
FP_A, FP_B, FP_C = "1" * 32, "2" * 32, "3" * 32


def seat_list_token(key=VENDOR_KEY, **overrides):
    payload = {
        "expires": "2027-01-03", "issued": "2026-10-05T08:30:00Z", "kind": seat_list.SEAT_LIST_KIND,
        "license_id": "LP-TEST-0001", "machine_id": MACHINE, "max_stations": 3, "stations": [FP_A, FP_B],
    }
    payload.update(overrides)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return b64url_encode(raw) + "." + b64url_encode(key.sign(raw))


class SeatListContractTests(TestCase):
    def test_the_cross_language_fixture_verifies(self):
        value = seat_list.verify_seat_list(FIXTURE["token"], FIXTURE["public_key_hex"])
        payload = FIXTURE["payload"]
        self.assertEqual(
            (value.license_id, value.machine_id, value.max_stations, list(value.stations), value.issued, value.expires.isoformat()),
            (payload["license_id"], payload["machine_id"], payload["max_stations"], payload["stations"], payload["issued"], payload["expires"]),
        )
        self.assertTrue(value.lists(FIXTURE["listed_fingerprint"]))
        self.assertFalse(value.lists(FIXTURE["unlisted_fingerprint"]))
        body, signature = FIXTURE["token"].split(".")
        tampered = signature[:-2] + ("BA" if signature.endswith("AA") else "AA")
        with self.assertRaises(Exception):
            seat_list.verify_seat_list(body + "." + tampered, FIXTURE["public_key_hex"])
        with self.assertRaises(Exception):
            seat_list.verify_seat_list(FIXTURE["token"], VENDOR_PUBLIC_HEX)

    def test_lists_outside_the_contract_are_refused(self):
        for overrides in (
            {"stations": [FP_B, FP_A]},                       # not sorted
            {"stations": [FP_A, FP_A]},                       # not unique
            {"max_stations": 1},                              # more stations than seats
            {"kind": "labelpilot-license"},
            {"stations": ["xyz"]},
            {"issued": "2026-10-05"},
            {"extra": True},
        ):
            with self.assertRaises(ValueError, msg=overrides):
                seat_list.verify_seat_list(seat_list_token(**overrides), VENDOR_PUBLIC_HEX)
        # A licence token is not a seat list.
        with self.assertRaises(ValueError):
            seat_list.verify_seat_list(signed(), VENDOR_PUBLIC_HEX)


class SeatListTests(LicenceTestCase):
    def setUp(self):
        super().setUp()
        self.list_path = self.root / "license-seats.lst"
        self.link_path = self.root / "license-seats.link"
        patcher = mock.patch.dict(os.environ, {
            "LABELPILOT_SEAT_LIST_PATH": str(self.list_path),
            "LABELPILOT_SEAT_LIST_LINK_PATH": str(self.link_path),
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        seat_list.reset_cache()
        self.addCleanup(seat_list.reset_cache)

    def station(self, name, fingerprint, state="active"):
        from label_stations.models import LabelsStations
        return LabelsStations.objects.create(
            station_name=name, station_ip=f"192.0.2.{LabelsStations.objects.count() + 10}",
            seat_state=state, station_fingerprint=fingerprint,
        )

    def test_only_a_newer_list_of_this_licence_is_installed(self):
        self.install(features=["seat-list"])
        with self.on("2026-10-06"):
            seat_list.install(seat_list_token())
            for token in (
                seat_list_token(license_id="LP-OTHER-0002"),
                seat_list_token(machine_id="b" * 32),
                seat_list_token(issued="2026-10-01T00:00:00Z"),
                seat_list_token(Ed25519PrivateKey.generate(), issued="2026-10-07T00:00:00Z"),
            ):
                with self.assertRaises(Exception, msg=token):
                    seat_list.install(token)
            self.assertEqual(self.list_path.read_text(encoding="utf-8"), seat_list_token())
            seat_list.install(seat_list_token(issued="2026-10-06T00:00:00Z", stations=[FP_A]))
            self.assertEqual(seat_list.current().stations, (FP_A,))

    def test_stations_outside_the_list_receive_no_data(self):
        from licensing import seats
        self.install(features=["seat-list"])
        listed, unlisted = self.station("Line 1", FP_A), self.station("Line 2", FP_C)
        legacy = self.station("Line 3", "")
        with self.on("2026-10-06"):
            # No list yet: nobody gets data.
            for line in (listed, unlisted, legacy):
                with self.assertRaises(seats.SeatError):
                    seats.ensure_may_receive_data(line)
            self.assertEqual(seats.seat_list_state(listed), "no_list")
            seat_list.install(seat_list_token())
            seats.ensure_may_receive_data(listed)
            for line in (unlisted, legacy):
                with self.assertRaises(seats.SeatError) as denied:
                    seats.ensure_may_receive_data(line)
                self.assertEqual(denied.exception.code, "station.notInSeatList")
            self.assertEqual(seats.seat_list_state(listed), "listed")
            self.assertEqual(seats.seat_list_state(unlisted), "unlisted")
            self.assertEqual(seat_list.push_token(), seat_list_token())
        with self.on("2027-01-04"):  # the day after the list expires
            with self.assertRaises(seats.SeatError):
                seats.ensure_may_receive_data(listed)
            self.assertTrue(seat_list.status()["expired"])

    def test_a_licence_without_the_feature_needs_no_list(self):
        from licensing import seats
        self.install()
        line = self.station("Line 1", FP_C)
        with self.on("2026-10-06"):
            seats.ensure_may_receive_data(line)
            self.assertIsNone(seats.seat_list_state(line))
            self.assertIsNone(seat_list.push_token())
            self.assertEqual(seat_list.sync().status, seat_list.NOT_REQUIRED)

    def test_sync_sends_the_seated_stations_and_links_the_server(self):
        self.install(features=["seat-list"])
        self.station("Line 1", FP_A)
        self.station("Line 2", FP_B)
        self.station("Waiting", FP_C, state="pending")
        self.station("Legacy", "")
        sent = []

        def vendor(body, timeout):
            sent.append(body)
            return {"status": "ok", "token": seat_list_token(issued=f"2026-10-06T00:00:0{len(sent)}Z")}

        with self.on("2026-10-06"), mock.patch.object(seat_list, "_post", side_effect=vendor):
            self.assertEqual(seat_list.sync().status, seat_list.UPDATED)
            self.assertEqual(seat_list.sync().status, seat_list.UPDATED)
            status = seat_list.status()
        self.assertEqual(sent[0]["stations"], [FP_A, FP_B])
        self.assertEqual((sent[0]["license_id"], sent[0]["machine_id"]), ("LP-TEST-0001", MACHINE))
        self.assertRegex(sent[0]["sync_secret"], r"^[0-9a-f]{64}$")
        self.assertEqual(sent[0]["sync_secret"], sent[1]["sync_secret"])
        self.assertEqual(self.link_path.read_text(encoding="utf-8"), sent[0]["sync_secret"])
        self.assertTrue(status["in_sync"] and status["linked"] and status["present"])
        self.assertEqual(status["last_sync"]["status"], seat_list.UPDATED)

    def test_sync_failures_keep_the_installed_list(self):
        self.install(features=["seat-list"])
        with self.on("2026-10-06"):
            seat_list.install(seat_list_token())
            forged = seat_list_token(Ed25519PrivateKey.generate(), issued="2026-10-07T00:00:00Z")
            for answer, expected in (
                ({"status": "rejected", "code": "release_limit"}, (seat_list.REJECTED, "release_limit")),
                ({"status": "not_found"}, (seat_list.NOT_FOUND, "")),
                ({"status": "ok", "token": forged}, (seat_list.REJECTED, "install")),
            ):
                with mock.patch.object(seat_list, "_post", return_value=answer):
                    result = seat_list.sync()
                self.assertEqual((result.status, result.detail), expected)
            with mock.patch.object(seat_list, "_post", side_effect=OSError("offline")):
                self.assertEqual(seat_list.sync().status, seat_list.UNAVAILABLE)
            with mock.patch.dict(os.environ, {"SEAT_LIST_SYNC": "0"}):
                self.assertEqual(seat_list.sync().status, seat_list.DISABLED)
            self.assertEqual(self.list_path.read_text(encoding="utf-8"), seat_list_token())

    def test_offline_request_and_import_endpoints_are_for_administrators(self):
        self.install(features=["seat-list"])
        self.station("Line 1", FP_A)
        client = APIClient()
        self.assertIn(client.get("/api/v1/license/seat-list/request/").status_code, (401, 403))
        denied = client.post("/api/v1/license/seat-list/import/", {"token": seat_list_token()}, format="json")
        self.assertIn(denied.status_code, (401, 403))
        client.force_authenticate(get_user_model().objects.create_superuser("chief", password="x"))
        with self.on("2026-10-06"):
            request = client.get("/api/v1/license/seat-list/request/")
            self.assertEqual(request.status_code, 200)
            document = json.loads(request.content)
            self.assertEqual(document["kind"], seat_list.SEAT_REQUEST_KIND)
            self.assertEqual(
                (document["license_id"], document["machine_id"], document["stations"]),
                ("LP-TEST-0001", MACHINE, [FP_A]),
            )
            other = seat_list_token(license_id="LP-OTHER-0002")
            self.assertEqual(client.post("/api/v1/license/seat-list/import/", {"token": other}, format="json").status_code, 400)
            good = client.post("/api/v1/license/seat-list/import/", {"token": seat_list_token()}, format="json")
            self.assertEqual(good.status_code, 200)
            self.assertTrue(good.json()["seat_list"]["present"])
            older = seat_list_token(issued="2026-10-01T00:00:00Z")
            self.assertEqual(client.post("/api/v1/license/seat-list/import/", {"token": older}, format="json").status_code, 400)
