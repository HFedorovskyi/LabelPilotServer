"""Commissioning command: flip strict licensing on/off safely.

`enable_strict_licensing` writes LICENSE_REQUIRED=true into backend/.env ONLY when a
valid, machine-matched license is already installed — so a rollout can never brick a
box that has not been licensed yet. Restart the LabelPilot service for it to take effect
(settings are read at startup).

  python manage.py enable_strict_licensing            # guarded enable
  python manage.py enable_strict_licensing --status   # show license + strict state
  python manage.py enable_strict_licensing --disable  # back to lenient
  python manage.py enable_strict_licensing --force     # enable despite a failed check (NOT recommended)
"""
import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def _effective_strict() -> bool:
    return bool(getattr(settings, "LICENSE_REQUIRED", False)) and not getattr(settings, "DEBUG", False)


def _set_env(env_path: Path, key: str, value: str) -> None:
    """Idempotently set KEY=value in the .env, preserving every other line. Atomic write."""
    lines = []
    found = False
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
            stripped = raw.lstrip()
            if stripped.startswith(key + "=") or stripped.startswith(key + " ="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(raw)
    if not found:
        lines.append(f"{key}={value}")
    content = "\n".join(lines) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(env_path.parent), suffix=".env.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, env_path)  # atomic on NTFS
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


class Command(BaseCommand):
    help = "Enable strict licensing (LICENSE_REQUIRED=true) — only if a valid, machine-matched license is installed."

    def add_arguments(self, parser):
        parser.add_argument("--status", action="store_true", help="Show license + strict status and exit")
        parser.add_argument("--disable", action="store_true", help="Set LICENSE_REQUIRED=false (back to lenient)")
        parser.add_argument("--force", action="store_true", help="Enable even if the license check fails (NOT recommended)")

    def handle(self, *args, **options):
        from licensing.core import license_state, machine_id
        st = license_state()
        env_path = Path(settings.BASE_DIR) / ".env"

        if options["status"]:
            self.stdout.write(f"machine_id        : {machine_id()}")
            self.stdout.write(
                f"license           : present={st.present} signature_valid={st.signature_valid} "
                f"machine_ok={st.machine_ok} expired={st.expired}"
            )
            self.stdout.write(f"LICENSE_REQUIRED  : {getattr(settings, 'LICENSE_REQUIRED', False)}")
            self.stdout.write(f"effective strict  : {_effective_strict()}  (strict = LICENSE_REQUIRED and not DEBUG)")
            return

        if options["disable"]:
            _set_env(env_path, "LICENSE_REQUIRED", "false")
            self.stdout.write(self.style.WARNING("LICENSE_REQUIRED=false written. Restart the LabelPilot service to apply."))
            return

        # Guarded enable.
        if not options["force"]:
            if not st.valid_for_key:
                raise CommandError(
                    f"Refusing to enable strict licensing: no valid license is installed "
                    f"(present={st.present}, signature_valid={st.signature_valid}). "
                    f"Install a valid license.lpl next to .env first, then re-run. (Override: --force.)"
                )
            if not st.machine_ok:
                raise CommandError(
                    f"Refusing: the installed license is bound to a DIFFERENT machine. "
                    f"This machine_id is {machine_id()}; ask the vendor to issue a license bound to it. "
                    f"(Override: --force.)"
                )

        _set_env(env_path, "LICENSE_REQUIRED", "true")
        self.stdout.write(self.style.SUCCESS("LICENSE_REQUIRED=true written. Restart the LabelPilot service to apply."))
        if st.expired:
            self.stdout.write(self.style.WARNING(
                "Note: the installed license is EXPIRED. Decryption/printing keep working; only NEW seats are blocked."
            ))
        if st.valid_for_key and st.license is not None and st.license.machine_id is None:
            self.stdout.write(self.style.WARNING(
                "Note: this license is UNBOUND (works on any machine). Consider a machine-bound license for anti-sharing."
            ))
