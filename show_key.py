import os
import sys
import django
import hashlib
import binascii

sys.path.append('d:/Antigravity_Workspaces/LabelPilot_Server/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LabelPilotServer.settings')
django.setup()

from django.conf import settings

def show_key():
    secret_key = settings.SECRET_KEY
    # The key is SHA-256 of the secret key string
    key_bytes = hashlib.sha256(secret_key.encode('utf-8')).digest()
    key_hex = binascii.hexlify(key_bytes).decode('utf-8')
    key_base64 = binascii.b2a_base64(key_bytes).decode('utf-8').strip()

    print("\n" + "="*50)
    print("ENCRYPTION KEY DETAILS (AES-256-CBC)")
    print("="*50)
    print(f"Algorithm:      AES-256-CBC")
    print(f"Key Derivation: SHA-256(settings.SECRET_KEY)")
    print(f"SECRET_KEY:     {secret_key}")
    print("-" * 50)
    print(f"Derived Key (Hex) [For Client]:\n{key_hex}")
    print("-" * 50)
    print(f"Derived Key (Base64):\n{key_base64}")
    print("="*50 + "\n")

if __name__ == "__main__":
    show_key()
