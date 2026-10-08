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
