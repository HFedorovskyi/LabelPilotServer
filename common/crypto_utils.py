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
    # Derive a 32-byte (256-bit) key from SECRET_KEY
    return hashlib.sha256(settings.SECRET_KEY.encode()).digest()

def encrypt_data(data: dict) -> bytes:
    """
    Encrypts a dictionary into a bytes object using AES-256-CBC.
    Format: [IV (16 bytes)] + [Encrypted Data (PKCS7 padded)]
    """
    json_str = json.dumps(data)
    data_bytes = json_str.encode('utf-8')
    
    key = get_key()
    iv = os.urandom(16)
    
    # Pad data (AES block size is 128 bits = 16 bytes)
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(data_bytes) + padder.finalize()
    
    # Encrypt
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    
    # Prepend IV
    return iv + ciphertext

def decrypt_data(encrypted_data_with_iv: bytes) -> dict:
    """
    Decrypts bytes into a dictionary using AES-256-CBC.
    Expects format: [IV (16 bytes)] + [Encrypted Data]
    """
    if len(encrypted_data_with_iv) < 16:
        raise ValueError("Data too short to contain IV")
        
    iv = encrypted_data_with_iv[:16]
    ciphertext = encrypted_data_with_iv[16:]
    key = get_key()
    
    # Decrypt
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()
    
    # Unpad
    unpadder = padding.PKCS7(128).unpadder()
    data_bytes = unpadder.update(padded_data) + unpadder.finalize()
    
    return json.loads(data_bytes.decode('utf-8'))

