"""Password rules for server users: the validators in settings.AUTH_PASSWORD_VALIDATORS plus
a check Django misses, answered in the request's language. Used wherever a password is set:
the first admin, «Доступ к серверу», the reset tool on the server computer."""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from api.i18n import tr

# In the order a person fixes them.
_PROBLEMS = (
    ("password_too_short", "user.passwordTooShort"),
    ("password_entirely_numeric", "user.passwordNumeric"),
    ("password_too_similar", "user.passwordSimilar"),
    ("password_too_common", "user.passwordCommon"),
)


def password_problem(password, user):
    """Why the password is too weak, or None. `user` may be unsaved (a new account)."""
    codes = set()
    try:
        validate_password(password, user)
    except ValidationError as e:
        codes = {err.code for err in e.error_list} or {"weak"}
    # Django's similarity check misses a short login inside a longer password ("olga2026olga").
    login = (user.username or "").lower()
    if len(login) >= 3 and login in password.lower():
        codes.add("password_too_similar")
    for code, key in _PROBLEMS:
        if code in codes:
            return tr(key)
    return tr("user.passwordWeak") if codes else None
