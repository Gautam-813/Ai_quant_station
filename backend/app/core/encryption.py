"""
Encryption utility for user API keys.
Uses Fernet (symmetric encryption) with the app's SECRET_KEY.
"""
from cryptography.fernet import Fernet
import base64
import hashlib

def _derive_key(secret: str) -> bytes:
    """Derive a valid Fernet key from SECRET_KEY."""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def encrypt_api_key(api_key: str, secret_key: str) -> str:
    """Encrypt an API key for storage."""
    f = Fernet(_derive_key(secret_key))
    return f.encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted: str, secret_key: str) -> str:
    """Decrypt a stored API key."""
    f = Fernet(_derive_key(secret_key))
    return f.decrypt(encrypted.encode()).decode()
