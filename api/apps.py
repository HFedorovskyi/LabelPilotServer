from django.apps import AppConfig

class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        # Register the strict-licensing system check (api is already installed).
        from . import checks  # noqa: F401
        # One-line boot log so a misconfigured strict rollout is visible immediately.
        # LOG ONLY: never raise, no DB access, no get_key()/encryption here.
        try:
            from django.conf import settings
            import logging
            log = logging.getLogger('licensing')
            if getattr(settings, 'LICENSE_REQUIRED', False):
                from licensing.core import license_state
                from licensing.enforcement import commercial_license_ok
                st = license_state()
                ok, reason = commercial_license_ok()
                log.log(
                    logging.INFO if ok else logging.CRITICAL,
                    'LICENSE_REQUIRED=on commercial_ok=%s reason=%s present=%s signature_valid=%s machine_ok=%s expired=%s',
                    ok, reason, st.present, st.signature_valid, st.machine_ok, st.expired,
                )
            else:
                from licensing.integrity import integrity_ok
                if not integrity_ok():
                    log.warning('licensing integrity check failed (lenient mode — export still gated)')
        except Exception:
            pass
