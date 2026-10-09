"""Server users («Доступ к серверу»): the fields the page shows, password rules and the
session of an admin who changes their own password."""
from django.contrib.auth.models import Group, User
from django.test import TestCase
from rest_framework.test import APIClient

from api.auth_views import ensure_groups

USERS = "/api/v1/users/"
GOOD = "luna-kora-47"


class UserManagementTests(TestCase):
    def setUp(self):
        ensure_groups()
        self.admin = User.objects.create_user("chief", password=GOOD)
        self.admin.groups.add(Group.objects.get(name="admin"))
        self.client = APIClient()
        self.client.login(username="chief", password=GOOD)

    def create(self, **data):
        return self.client.post(USERS, {"username": "olga", "password": GOOD, "role": "manager", **data}, format="json")

    def test_list_has_name_and_sign_in_dates(self):
        self.client.post("/api/v1/auth/login/", {"username": "chief", "password": GOOD}, format="json")
        row = self.client.get(USERS).json()[0]
        self.assertEqual(row["username"], "chief")
        self.assertEqual(row["name"], "")
        self.assertIsNotNone(row["last_login"])
        self.assertIsNotNone(row["date_joined"])

    def test_create_keeps_the_name(self):
        res = self.create(name="  Ольга, технолог  ")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["name"], "Ольга, технолог")
        self.assertIsNone(res.json()["last_login"])

    def test_create_refuses_weak_passwords(self):
        for password, reason in (
            ("kora-47", "короче 8"),
            ("20261008", "из одних цифр"),
            ("olga2026olga", "похож на логин"),
            ("password123", "распространённый"),
        ):
            with self.subTest(password=password):
                res = self.create(password=password)
                self.assertEqual(res.status_code, 400)
                self.assertIn(reason, res.json()["detail"])
        self.assertFalse(User.objects.filter(username="olga").exists())

    def test_password_change_is_checked_too(self):
        user = User.objects.get(id=self.create().json()["id"])
        res = self.client.patch(f"{USERS}{user.id}/", {"password": "12345678"}, format="json")
        self.assertEqual(res.status_code, 400)
        user.refresh_from_db()
        self.assertTrue(user.check_password(GOOD))

    def test_name_can_be_changed_and_cleared(self):
        user_id = self.create(name="Мастер").json()["id"]
        res = self.client.patch(f"{USERS}{user_id}/", {"name": "Мастер смены 2"}, format="json")
        self.assertEqual(res.json()["name"], "Мастер смены 2")
        res = self.client.patch(f"{USERS}{user_id}/", {"name": ""}, format="json")
        self.assertEqual(res.json()["name"], "")

    def test_admin_changing_own_password_stays_signed_in(self):
        res = self.client.patch(f"{USERS}{self.admin.id}/", {"password": "vesta-mira-31"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)

    def test_new_password_ends_the_users_other_sessions(self):
        self.create()
        other = APIClient()
        other.login(username="olga", password=GOOD)
        self.assertEqual(other.get("/api/v1/auth/me/").status_code, 200)
        olga = User.objects.get(username="olga")
        self.client.patch(f"{USERS}{olga.id}/", {"password": "vesta-mira-31"}, format="json")
        self.assertEqual(other.get("/api/v1/auth/me/").status_code, 401)


LOGIN = "/api/v1/auth/login/"


class LoginThrottleTests(TestCase):
    def setUp(self):
        ensure_groups()
        self.user = User.objects.create_user("olga", password=GOOD)
        self.client = APIClient()

    def attempt(self, password, ip="10.0.0.5", username="olga"):
        return self.client.post(LOGIN, {"username": username, "password": password}, format="json", REMOTE_ADDR=ip)

    def test_five_wrong_passwords_close_the_login_on_that_computer(self):
        left = [self.attempt("wrong-one").json()["attempts_left"] for _ in range(4)]
        self.assertEqual(left, [4, 3, 2, 1])
        res = self.attempt("wrong-one")
        self.assertEqual(res.status_code, 429)
        self.assertGreater(res.json()["locked_for"], 800)
        self.assertIn("15", res.json()["detail"])
        # Locked: even the right password is not checked.
        self.assertEqual(self.attempt(GOOD).status_code, 429)
        # Another computer is not affected — a stranger cannot lock the real user out.
        self.assertEqual(self.attempt(GOOD, ip="10.0.0.9").status_code, 200)

    def test_a_good_sign_in_resets_the_count(self):
        self.attempt("wrong-one")
        self.attempt("wrong-one")
        self.assertEqual(self.attempt(GOOD).status_code, 200)
        self.assertEqual(self.attempt("wrong-one").json()["attempts_left"], 4)

    def test_twenty_wrong_logins_close_the_computer(self):
        for n in range(19):
            self.assertEqual(self.attempt("wrong-one", username=f"guess{n}").status_code, 401)
        self.assertEqual(self.attempt("wrong-one", username="guess19").status_code, 429)
        self.assertEqual(self.attempt(GOOD).status_code, 429)

    def test_a_lock_tells_the_admins(self):
        from notifications.models import Notification
        for _ in range(5):
            self.attempt("wrong-one")
        note = Notification.objects.get(code="auth.locked")
        self.assertEqual(note.params["login"], "olga")
        self.assertEqual(note.params["ip"], "10.0.0.5")
        self.assertEqual(note.link_tab, "users")

    def test_a_new_password_from_an_admin_lifts_the_lock(self):
        for _ in range(5):
            self.attempt("wrong-one")
        admin = User.objects.create_user("chief", password=GOOD)
        admin.groups.add(Group.objects.get(name="admin"))
        boss = APIClient()
        boss.login(username="chief", password=GOOD)
        boss.patch(f"{USERS}{self.user.id}/", {"password": "vesta-mira-31"}, format="json")
        self.assertEqual(self.attempt("vesta-mira-31").status_code, 200)


class BootstrapPasswordTests(TestCase):
    def test_the_first_admin_needs_a_real_password(self):
        client = APIClient()
        res = client.post("/api/v1/auth/bootstrap/", {"username": "admin", "password": "1"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(User.objects.exists())
        res = client.post("/api/v1/auth/bootstrap/", {"username": "admin", "password": GOOD}, format="json")
        self.assertEqual(res.status_code, 201)


class ResetPasswordCommandTests(TestCase):
    def test_sets_the_password_reopens_promotes_and_unlocks(self):
        from io import StringIO
        from unittest import mock

        from django.core.management import call_command

        from server_activity.models import LoginThrottle

        ensure_groups()
        User.objects.create_user("admin", password=GOOD).groups.add(Group.objects.get(name="admin"))
        olga = User.objects.create_user("olga", password=GOOD, is_active=False)
        olga.groups.add(Group.objects.get(name="manager"))
        LoginThrottle.objects.create(ip="10.0.0.5", username="olga", failures=0,
                                     last_failure_at=olga.date_joined, locked_until=olga.date_joined.replace(year=2100))
        out = StringIO()
        # Account 2 = olga; the first password breaks a rule, then a good one twice; yes to admin.
        with mock.patch("builtins.input", side_effect=["2", "д"]), \
                mock.patch("getpass.getpass", side_effect=["12345678", "vesta-mira-31", "vesta-mira-31"]):
            call_command("reset_password", "--lang", "ru", stdout=out)
        olga.refresh_from_db()
        self.assertTrue(olga.check_password("vesta-mira-31"))
        self.assertTrue(olga.is_active)
        self.assertTrue(olga.groups.filter(name="admin").exists())
        self.assertFalse(LoginThrottle.objects.filter(username="olga").exists())
        text = out.getvalue()
        self.assertIn("из одних цифр", text)
        self.assertIn("теперь администратор", text)


class SystemProxyTests(TestCase):
    """«Настройки» reach the updater (127.0.0.1:9000) only through these admin-checked views."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        ensure_groups()
        self.admin = User.objects.create_user("chief", password=GOOD)
        self.admin.groups.add(Group.objects.get(name="admin"))
        self.manager = User.objects.create_user("olga", password=GOOD)
        self.manager.groups.add(Group.objects.get(name="manager"))
        self.client = APIClient()

    def fake(self, status_code=200, body=None):
        from unittest import mock
        res = mock.Mock(status_code=status_code, ok=200 <= status_code < 300, text="")
        res.json.return_value = body or {}
        return res

    def test_only_admins_start_updates_backups_and_rollbacks(self):
        from unittest import mock
        self.client.force_authenticate(self.manager)
        with mock.patch("api.system_views.requests.request") as call:
            self.assertEqual(self.client.post("/api/v1/system/update/").status_code, 403)
            self.assertEqual(self.client.post("/api/v1/system/backups/").status_code, 403)
            self.assertEqual(self.client.post("/api/v1/system/backups/v1.1.34_20261005_180200/restore/").status_code, 403)
            call.assert_not_called()
        self.client.force_authenticate(self.admin)
        with mock.patch("api.system_views.requests.request", return_value=self.fake(200, {"message": "Rollback started"})) as call:
            res = self.client.post("/api/v1/system/backups/v1.1.34_20261005_180200/restore/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(call.call_args.kwargs["json"], {"backup_id": "v1.1.34_20261005_180200"})
        self.assertTrue(call.call_args.args[1].startswith("http://127.0.0.1:9000/"))

    def test_update_check_is_cached_and_says_when_the_updater_is_down(self):
        from unittest import mock
        import requests
        self.client.force_authenticate(self.manager)
        body = {"available": True, "version": "1.1.36", "changelog": "x", "published_at": "2026-10-06", "download_url": "u"}
        with mock.patch("api.system_views.requests.request", return_value=self.fake(200, body)) as call:
            first = self.client.get("/api/v1/system/update/").json()
            self.client.get("/api/v1/system/update/")
            self.assertEqual(call.call_count, 1)
        self.assertTrue(first["available"])
        self.assertTrue(first["has_package"])
        from django.core.cache import cache
        cache.clear()
        with mock.patch("api.system_views.requests.request", side_effect=requests.ConnectionError("refused")):
            down = self.client.get("/api/v1/system/update/").json()
            self.assertEqual(self.client.get("/api/v1/system/backups/").status_code, 503)
        self.assertEqual(down["updater"], "offline")
        self.assertIsNone(down["available"])

    def test_an_update_file_is_streamed_to_the_updater(self):
        from unittest import mock
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_authenticate(self.admin)
        sent = {}

        def capture(method, url, timeout, data, headers):
            sent["body"] = b"".join(data)
            sent["type"] = headers["Content-Type"]
            return self.fake(200, {"message": "Offline update started"})

        with mock.patch("api.system_views.requests.request", side_effect=capture):
            res = self.client.post("/api/v1/system/update/file/",
                                   {"file": SimpleUploadedFile("LabelPilot-1.1.36.lpupdate", b"PK-signed-bytes")})
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"PK-signed-bytes", sent["body"])
        self.assertIn(b'filename="LabelPilot-1.1.36.lpupdate"', sent["body"])
        self.assertTrue(sent["type"].startswith("multipart/form-data; boundary="))


class LicenceRefreshRecordTests(TestCase):
    def test_the_last_check_shows_on_the_licence_status(self):
        from licensing.refresh import refresh_license
        result = refresh_license()
        data = APIClient().get("/api/v1/license/").json()
        self.assertEqual(data["refresh_last"]["status"], result.status)
        self.assertTrue(data["refresh_last"]["at"].endswith("Z"))

    def test_no_licence_file_is_reported_as_none(self):
        self.assertEqual(APIClient().get("/api/v1/license/").json()["license_file"], "none")


class UpdaterUpkeepTests(TestCase):
    """After an update from 1.1.34 the old updater keeps running; the server restarts it once idle."""

    def answers(self, status, progress=None):
        from unittest import mock

        def get(url, timeout):
            body = status if url.endswith("/status") else (progress or {"status": "idle"})
            return mock.Mock(json=mock.Mock(return_value=body))
        return get

    def test_restarts_an_old_idle_updater_and_leaves_the_rest(self):
        from unittest import mock
        import requests
        from api import updater_upkeep as u
        done = mock.Mock(returncode=0, stderr=b"")
        with mock.patch.object(u.requests, "get", side_effect=self.answers({"service": "LabelPilot Updater"})), \
                mock.patch.object(u, "NSSM", mock.Mock(exists=mock.Mock(return_value=True), __str__=lambda s: "nssm.exe")), \
                mock.patch.object(u.subprocess, "run", return_value=done) as run:
            self.assertEqual(u.check_once(), "restarted")
        self.assertEqual(run.call_args.args[0][1:], ["restart", "LabelPilotUpdater"])
        with mock.patch.object(u.requests, "get", side_effect=self.answers({"api": 2})):
            self.assertEqual(u.check_once(), "current")
        with mock.patch.object(u.requests, "get", side_effect=self.answers({}, {"status": "running"})):
            self.assertEqual(u.check_once(), "busy")
        with mock.patch.object(u.requests, "get", side_effect=requests.ConnectionError("refused")):
            self.assertEqual(u.check_once(), "down")
