"""Create the first admin user non-interactively (for the native installer / headless).

No-op if any user already exists, so it is safe to run on every install. Mirrors the
self-disabling /api/v1/auth/bootstrap endpoint for the browser flow.

  python manage.py bootstrap_admin --username admin --password '...'
  # or via env: LP_ADMIN_USER / LP_ADMIN_PASSWORD
"""
import os

from django.contrib.auth.models import User, Group
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the first admin user (no-op if any user already exists)."

    def add_arguments(self, parser):
        parser.add_argument("--username", default=None)
        parser.add_argument("--password", default=None)

    def handle(self, *args, **options):
        if User.objects.exists():
            self.stdout.write("Users already exist — bootstrap_admin is a no-op.")
            return
        username = options["username"] or os.environ.get("LP_ADMIN_USER")
        password = options["password"] or os.environ.get("LP_ADMIN_PASSWORD")
        if not username or not password:
            raise CommandError(
                "Provide --username/--password or LP_ADMIN_USER/LP_ADMIN_PASSWORD env vars."
            )
        for name in ("admin", "manager"):
            Group.objects.get_or_create(name=name)
        user = User.objects.create_superuser(username=username, password=password)
        user.groups.add(Group.objects.get(name="admin"))
        self.stdout.write(self.style.SUCCESS(f"Created admin user '{username}'."))
