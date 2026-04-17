"""
AES-GCM encryption for email passwords stored in the database.
Uses the `cryptography` library (already installed as a dependency of python-jose).
No additional packages needed.
"""
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.backends import default_backend

_password = os.environ.get("EMAIL_ENCRYPTION_KEY", "invoiceiq-default-key-change-in-prod").encode()
_salt = os.environ.get("EMAIL_ENCRYPTION_SALT", "invoiceiq-salt-v1").encode()

# Derive a 32-byte key using scrypt
_kdf = Scrypt(salt=_salt, length=32, n=2**14, r=8, p=1, backend=default_backend())
_key = _kdf.derive(_password)


def encrypt_password(plain: str) -> str:
    """Encrypt a plain-text password. Returns base64-encoded nonce+ciphertext."""
    if not plain:
        return ""
    nonce = os.urandom(12)  # 96-bit nonce for AES-GCM
    aesgcm = AESGCM(_key)
    ciphertext = aesgcm.encrypt(nonce, plain.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_password(encrypted: str) -> str:
    """Decrypt a stored password. Falls back to plain text for backward compatibility."""
    if not encrypted:
        return ""
    try:
        data = base64.b64decode(encrypted)
        nonce, ciphertext = data[:12], data[12:]
        aesgcm = AESGCM(_key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode()
    except Exception:
        # Backward compat — row stored as plain text before encryption was added
        return encrypted
