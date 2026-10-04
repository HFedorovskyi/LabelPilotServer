"""Subscription grace, the trusted licence clock and licence refresh
(licensing/core.py, clock.py, refresh.py)."""
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

from licensing import clock, core, refresh
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
