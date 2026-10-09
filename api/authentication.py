from rest_framework.authentication import SessionAuthentication


class SessionAuthentication401(SessionAuthentication):
    """SessionAuthentication that keeps a genuine 'not authenticated' as HTTP 401.

    DRF's default SessionAuthentication returns ``None`` from ``authenticate_header()``.
    That makes DRF DOWNGRADE an unauthenticated NotAuthenticated(401) to a 403 — which
    becomes indistinguishable from a *license*/*permission*/*CSRF* denial (also 403). The
    SPA's apiFetch wrapper needs to tell those apart: a 401 means "your session expired,
    drop to the login screen", a 403 means "you're logged in but this action is forbidden
    (no license / not allowed) — show an error, do NOT log out".

    Returning a (non-Basic, custom) scheme keeps the status at 401 without triggering a
    native browser credential prompt (browsers only prompt for Basic/Digest/NTLM/Negotiate).
    CSRF failures still raise PermissionDenied(403) inside authenticate(), so an expired
    CSRF token on a logged-in user is surfaced as an error rather than a spurious logout.
    """

    def authenticate_header(self, request):
        return "Session"
