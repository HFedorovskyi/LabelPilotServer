"""Start menu entry «LabelPilot — сброс пароля» for reset-password.cmd. The server makes it
when it starts (serve.py), so installs that only take signed updates get it too; the
installer removes the LabelPilot folder on uninstall. Windows installs only, best effort:
a missing shortcut must never stop the server."""
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

from api.i18n import set_lang, tr

log = logging.getLogger(__name__)

BACKEND = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND / "reset-password.cmd"
ICON = BACKEND.parent.parent / "labelpilot.ico"


def _folder() -> Path:
    programs = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return programs / "LabelPilot"


def _ps_quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def ensure_reset_shortcut() -> None:
    from api.management.commands.reset_password import system_lang

    set_lang(system_lang())
    folder = _folder()
    link = folder / f"{tr('reset.title')}.lnk"
    if link.exists() or not SCRIPT.exists():
        return
    folder.mkdir(parents=True, exist_ok=True)
    command = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut({link}); "
        "$s.TargetPath = {target}; $s.WorkingDirectory = {cwd}; "
        "{icon}$s.Save()"
    ).format(
        link=_ps_quote(link), target=_ps_quote(SCRIPT), cwd=_ps_quote(BACKEND),
        icon=f"$s.IconLocation = {_ps_quote(ICON)}; " if ICON.exists() else "",
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                   capture_output=True, timeout=30, check=True)
    log.info("start menu shortcut created: %s", link)


def ensure_in_background() -> None:
    if sys.platform != "win32":
        return

    def run():
        try:
            ensure_reset_shortcut()
        except Exception:  # pragma: no cover - best effort, logged
            log.exception("could not create the password-reset shortcut")

    threading.Thread(target=run, name="start-menu", daemon=True).start()
