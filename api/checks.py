"""Startup visibility for strict licensing.

Registered from api.apps.ApiConfig.ready() (api is already in INSTALLED_APPS, so we
avoid adding 'licensing' as an app just for a log line). Uses Warning, never Error, so
`manage.py migrate` / `collectstatic` / `runserver` are NEVER blocked — hard enforcement
stays lazy in common.crypto_utils.get_key()."""
from django.conf import settings
from django.core.checks import Warning, register


@register()
def license_check(app_configs, **kwargs):
    warnings = []
    try:
        from licensing.integrity import integrity_ok, load_expected
        if getattr(settings, "LICENSE_REQUIRED", False) and not getattr(settings, "DEBUG", False):
            if load_expected() is None:
                warnings.append(Warning(
                    "LICENSE_REQUIRED is on but licensing/_fingerprint.json is missing. "
                    "Rebuild the installer (fingerprint step) or exports will be denied.",
                    id="licensing.W002",
                ))
            elif not integrity_ok(force_reload=True):
                warnings.append(Warning(
                    "Licensing integrity fingerprint MISMATCH — critical modules were modified "
                    "after the release build. Commercial export is denied until the build is restored.",
                    id="licensing.W003",
                ))
    except Exception:
        pass

    if not getattr(settings, "LICENSE_REQUIRED", False):
        return warnings
    try:
        from licensing.core import license_state
        st = license_state()
    except Exception:
        return warnings  # never let the check itself break a management command
    if st.valid_for_key:
        return warnings
    if not st.present:
        msg = ("LICENSE_REQUIRED is on but NO license file is installed. Commercial "
               "encrypt/export is denied until a valid license.lpl is installed.")
    else:
        msg = ("LICENSE_REQUIRED is on and the installed license is INVALID (bad "
               "signature or wrong machine). Minting encrypted artifacts will fail until fixed.")
    warnings.append(Warning(msg, id="licensing.W001"))
    return warnings
