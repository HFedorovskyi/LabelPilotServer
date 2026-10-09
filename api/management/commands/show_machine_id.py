"""Print this server's machine_id.

Commissioning step: the customer runs this and sends the value to the vendor, who
issues a machine-bound license (make_license.py issue --machine-id <id>). Binding is
the anti-sharing control — an unbound license works on any machine."""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Print this server's machine_id (send it to the vendor for a machine-bound license)."

    def handle(self, *args, **options):
        from licensing.core import machine_id
        self.stdout.write(machine_id())
