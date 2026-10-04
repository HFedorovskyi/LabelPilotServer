"""Django startup diagnostics for strict production licensing."""
from django.conf import settings
from django.core.checks import Warning, register


@register()
def license_check(app_configs, **kwargs):
    warnings = []
    strict = bool(getattr(settings, "LICENSE_REQUIRED", False)) or not bool(
        getattr(settings, "DEBUG", False)
    )

    if strict:
        try:
            from licensing.integrity import fingerprint_path, integrity_status

            status = integrity_status()
            if not fingerprint_path().is_file():
                warnings.append(
                    Warning(
                        "Production build is missing licensing/_fingerprint.lpf. "
                        "Commercial exports remain locked until a signed release is installed.",
                        id="licensing.W002",
                    )
                )
            elif not status.get("integrity_ok") or not status.get("signature_valid"):
                warnings.append(
                    Warning(
                        "Signed licensing integrity verification failed. "
                        "Commercial exports remain locked until the release files are restored.",
                        id="licensing.W003",
                    )
                )
        except Exception as exc:
            warnings.append(
                Warning(
                    f"Signed licensing integrity check failed to run: {exc}",
                    id="licensing.W003",
                )
            )

        try:
            from licensing.native_guard import verify_license_native

            native = verify_license_native(force_reload=True)
            if not native.available:
                warnings.append(
                    Warning(
                        "Native license guard or its signed manifest is missing. "
                        "Commercial exports remain locked.",
                        id="licensing.W004",
                    )
                )
            elif not native.ok and native.reason not in {
                "missing",
                "bad_signature",
                "wrong_machine",
                "expired",
            }:
                warnings.append(
                    Warning(
                        f"Native license guard rejected the installed release: {native.reason}.",
                        id="licensing.W005",
                    )
                )
        except Exception as exc:
            warnings.append(
                Warning(
                    f"Native license guard check failed to run: {exc}",
                    id="licensing.W004",
                )
            )

    if not strict:
        return warnings
    try:
        from licensing.core import license_state

        state = license_state()
    except Exception:
        return warnings
    if state.valid_for_key:
        return warnings
    if not state.present:
        message = (
            "Production licensing is active but no license file is installed. "
            "Commercial encryption/export remains locked."
        )
    else:
        message = (
            "Production licensing is active and the installed license has an invalid signature "
            "or machine binding. Commercial encryption/export remains locked."
        )
    warnings.append(Warning(message, id="licensing.W001"))
    return warnings
