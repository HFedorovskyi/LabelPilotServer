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
            if getattr(settings, 'LICENSE_REQUIRED', False):
                import logging
                from licensing.core import license_state
                st = license_state()
                logging.getLogger('licensing').log(
                    logging.INFO if st.valid_for_key else logging.CRITICAL,
                    'LICENSE_REQUIRED=on present=%s signature_valid=%s machine_ok=%s expired=%s',
                    st.present, st.signature_valid, st.machine_ok, st.expired,
                )
        except Exception:
            pass
