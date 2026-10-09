"""Lightweight per-request i18n for backend API messages (ru/en/de/uk).

Mirrors the rest of the system (plain dicts, no gettext/.mo toolchain — important for the
offline NSSM deploy). The request language is read from the `X-Lang` header by LangMiddleware
and stashed in a thread-local, so `tr(key, **params)` resolves the right language ANYWHERE
(views, DRF permissions, helper functions) without threading a `lang` argument around.

Messages live in api/messages.py (key -> {ru, en, de, uk}); missing locale falls back to ru,
missing key falls back to the key itself. Django's WSGI request handling is thread-per-request,
so the thread-local is request-isolated; the middleware resets it in a finally to avoid leaking
into a pooled thread's next request.
"""

import threading

from .messages import MESSAGES

LANGS = ("ru", "en", "de", "uk")
DEFAULT_LANG = "ru"

_state = threading.local()


def set_lang(lang: str) -> None:
    _state.lang = lang if lang in LANGS else DEFAULT_LANG


def get_lang() -> str:
    return getattr(_state, "lang", DEFAULT_LANG)


def lang_from_request(request) -> str:
    """X-Lang header wins; fall back to Accept-Language; default ru."""
    try:
        x = (request.headers.get("X-Lang") or "").strip().lower()[:2]
        if x in LANGS:
            return x
        al = (request.headers.get("Accept-Language") or "").strip().lower()[:2]
        return al if al in LANGS else DEFAULT_LANG
    except Exception:
        return DEFAULT_LANG


def tr(key: str, **params) -> str:
    """Translate a message key into the current request language, with {named} interpolation."""
    entry = MESSAGES.get(key)
    if not entry:
        return key
    text = entry.get(get_lang()) or entry.get(DEFAULT_LANG) or key
    if params:
        try:
            text = text.format(**params)
        except (KeyError, IndexError, ValueError):
            pass
    return text


class LangMiddleware:
    """Set the per-request language from the X-Lang header before the view runs."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_lang(lang_from_request(request))
        try:
            return self.get_response(request)
        finally:
            set_lang(DEFAULT_LANG)
