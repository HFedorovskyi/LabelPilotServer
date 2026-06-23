import json
import base64
import hashlib
import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from django.conf import settings

# In a real production scenario, this key should be loaded from environment variables
# or a secure vault. For this implementation, we will use a derived key from settings.SECRET_KEY
# to ensure consistent encryption across server restarts if not explicitly provided.

def get_key():
    """The data-encryption key.

    Lenient (default) or DEBUG: derive from a valid license if present, else fall back to
    the legacy SHA256(SECRET_KEY) key so pre-licensing / dev installs keep working.

    Strict (settings.LICENSE_REQUIRED and not DEBUG):
      - valid license present -> license-derived key (ignores expiry/machine by design, so
        a lapsed subscription or a transient machine_id() blip never bricks the line);
      - NO license present     -> legacy fallback (don't brick a box that hasn't been
        licensed yet or holds legacy-keyed data; the api system check + boot log flag it);
      - present BUT invalid (bad signature) -> raise LicenseError (fail closed: this is
        tamper evidence, not a missing license).

    The bare `except: pass` that used to swallow ALL errors into the legacy key is gone."""
    from licensing.core import license_state, derive_data_key, LicenseError
    st = license_state()
    strict = getattr(settings, "LICENSE_REQUIRED", False) and not getattr(settings, "DEBUG", False)

    if st.valid_for_key:
        return derive_data_key(st.license)
    if strict and st.present:
        raise LicenseError("Strict licensing: the installed license is invalid (signature).")
    return hashlib.sha256(settings.SECRET_KEY.encode()).digest()

def _license_token():
    """The raw signed license token (b64url(payload).b64url(sig)), or None if no license."""
    try:
        from licensing.core import load_license
        lic = load_license()
        return lic.token if lic is not None else None
    except Exception:
        return None


def encrypt_data(data: dict) -> bytes:
    """
    Encrypts a dict with AES-256-CBC. When a license is present the output is the
    self-describing LPI2 format that carries the (public, signed) license token, so the
    client can derive the SAME key and decrypt:
        b"LPI2\\n" + <license token ascii> + b"\\n" + [IV(16)] + [PKCS7-padded ciphertext]
    Without a license it is the legacy format: [IV(16)] + [ciphertext].
    """
    data_bytes = json.dumps(data).encode('utf-8')
    key = get_key()
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(data_bytes) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend()).encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()

    token = _license_token()
    if token:
        return b"LPI2\n" + token.encode("ascii") + b"\n" + iv + ciphertext
    return iv + ciphertext

def _key_from_token(token: str) -> bytes:
    """Derive the data key from a self-describing LPI2 token: verify its Ed25519
    signature, then derive. The ONE place that turns an embedded license into a key."""
    from licensing.core import _verify_and_parse, derive_data_key
    return derive_data_key(_verify_and_parse(token))  # raises InvalidSignature on forgery


def decrypt_data(blob: bytes) -> dict:
    """
    Decrypts an LPI2 or legacy AES-256-CBC blob into a dict.

    LPI2 (b"LPI2\\n" + token + b"\\n" + iv + ct) is SELF-DESCRIBING: the key is derived
    from the blob's OWN embedded, signature-verified token — INDEPENDENT of the server's
    installed license and of get_key(). This upholds "never hard-stop decryption": a
    properly-signed station report decrypts even on a server whose own license is
    absent/expired/wrong-machine. Legacy (iv + ct) uses get_key() (which may fail closed
    in strict mode for a present-but-tampered license).
    """
    if blob.startswith(b"LPI2\n"):
        rest = blob[len(b"LPI2\n"):]
        nl = rest.index(b"\n")
        token = rest[:nl].decode("ascii")
        blob = rest[nl + 1:]
        key = _key_from_token(token)  # raises InvalidSignature on a forged token
    else:
        key = get_key()  # legacy format; may raise LicenseError in strict mode

    if len(blob) < 16:
        raise ValueError("Data too short to contain IV")
    iv, ciphertext = blob[:16], blob[16:]
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend()).decryptor()
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    data_bytes = unpadder.update(padded_data) + unpadder.finalize()
    return json.loads(data_bytes.decode('utf-8'))

