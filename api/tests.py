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
