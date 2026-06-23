"""Startup visibility for strict licensing.

Registered from api.apps.ApiConfig.ready() (api is already in INSTALLED_APPS, so we
avoid adding 'licensing' as an app just for a log line). Uses Warning, never Error, so
`manage.py migrate` / `collectstatic` / `runserver` are NEVER blocked — hard enforcement
stays lazy in common.crypto_utils.get_key()."""
from django.conf import settings
from django.core.checks import Warning, register


@register()
def license_check(app_configs, **kwargs):
    if not getattr(settings, "LICENSE_REQUIRED", False):
        return []
    try:
        from licensing.core import license_state
        st = license_state()
    except Exception:
        return []  # never let the check itself break a management command
    if st.valid_for_key:
        return []
    if not st.present:
        msg = ("LICENSE_REQUIRED is on but NO license file is installed. New encrypted "
               "artifacts will use the legacy fallback key and clients cannot pair. "
               "Install a valid license.lpl.")
    else:
        msg = ("LICENSE_REQUIRED is on and the installed license is INVALID (bad "
               "signature). Minting new encrypted artifacts will fail until it is fixed.")
    return [Warning(msg, id="licensing.W001")]
