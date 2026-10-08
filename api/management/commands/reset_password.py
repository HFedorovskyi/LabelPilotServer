"""Set a new password for a server user from the server computer itself — the way back in
for a sole administrator who forgot the password. Started by «LabelPilot — сброс пароля»
in the Start menu (native/reset-password.cmd, elevated), so only someone with Windows
administrator rights on the server can use it.

  python manage.py reset_password

Asks for the account and the new password (hidden, twice, same rules as the web page),
reopens a closed sign-in, offers to make a manager an administrator, lifts the locks left
by wrong passwords. Speaks the Windows display language (ru/en/de/uk, else en)."""
import ctypes
import getpass
import locale
import sys

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from api.auth_views import ensure_groups, role_of
from api.i18n import LANGS, set_lang, tr
from api.login_throttle import clear_login
from api.passwords import password_problem

ADDRESS = "http://localhost:8000"
YES = {"y", "yes", "д", "да", "j", "ja", "т", "так"}
# Primary language ids of GetUserDefaultUILanguage().
WINDOWS_LANGS = {0x19: "ru", 0x22: "uk", 0x07: "de", 0x09: "en"}


def system_lang():
    try:
        return WINDOWS_LANGS.get(ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF, "en")
    except (AttributeError, OSError):
        code = (locale.getlocale()[0] or "en")[:2].lower()
        return code if code in LANGS else "en"


class Command(BaseCommand):
    help = "Set a new password for a server user (run on the server computer)."

    def add_arguments(self, parser):
        parser.add_argument("--lang", choices=LANGS, default=None)

    def handle(self, *args, **options):
        set_lang(options["lang"] or system_lang())
        out = self.stdout.write
        out(tr("reset.title"))
        out("")
        users = list(User.objects.order_by("username"))
        if not users:
            out(tr("reset.noUsers", address=ADDRESS))
            return
        out(tr("reset.accounts"))
        for number, user in enumerate(users, 1):
            role = tr("reset.roleAdmin") if role_of(user) == "admin" else tr("reset.roleManager")
            closed = "" if user.is_active else f", {tr('reset.closed')}"
            name = f" ({user.first_name})" if user.first_name else ""
            out(f"  {number}. {user.username}{name} — {role}{closed}")
        out("")

        user = self._pick(users)
        if user is None:
            return
        password = self._password(user)
        make_admin = role_of(user) != "admin" and self._ask(tr("reset.makeAdmin", login=user.username))

        reopened = not user.is_active
        user.set_password(password)
        user.is_active = True
        user.save()
        if make_admin:
            ensure_groups()
            user.groups.set([Group.objects.get(name="admin")])
        clear_login(user.username)

        out("")
        if reopened:
            out(tr("reset.reopened", login=user.username))
        if make_admin:
            out(tr("reset.madeAdmin", login=user.username))
        out(tr("reset.unlocked"))
        out(self.style.SUCCESS(tr("reset.done", login=user.username, address=ADDRESS)))

    def _pick(self, users):
        while True:
            answer = self._input(tr("reset.pick")).strip()
            if not answer:
                return None
            if answer.isdigit() and 1 <= int(answer) <= len(users):
                return users[int(answer) - 1]
            self.stdout.write(tr("reset.badPick"))

    def _password(self, user):
        self.stdout.write(tr("reset.rule"))
        while True:
            first = getpass.getpass(tr("reset.password", login=user.username))
            problem = password_problem(first, user)
            if problem:
                self.stdout.write(problem)
                continue
            if getpass.getpass(tr("reset.repeat")) != first:
                self.stdout.write(tr("reset.mismatch"))
                continue
            return first

    def _ask(self, question):
        return self._input(question).strip().lower() in YES

    def _input(self, prompt):
        sys.stdout.flush()
        return input(prompt)
