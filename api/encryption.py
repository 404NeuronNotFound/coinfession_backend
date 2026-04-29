"""
Encryption utilities for API key storage.
Uses Fernet symmetric encryption (AES-128-CBC + HMAC).
"""
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def get_fernet():
    """
    Get Fernet instance from Django settings.
    Raises ImproperlyConfigured if FIELD_ENCRYPTION_KEY is not set.
    """
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
    
    if not key:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY is not set in Django settings. "
            "Generate one with: from cryptography.fernet import Fernet; Fernet.generate_key()"
        )
    
    # Convert to bytes if string
    if isinstance(key, str):
        key = key.encode()
    
    return Fernet(key)


def encrypt_key(plain_text: str) -> str:
    """
    Encrypt a plain text API key.
    
    Args:
        plain_text: The plain API key to encrypt
        
    Returns:
        The encrypted key as a string
    """
    return get_fernet().encrypt(plain_text.encode()).decode()


def decrypt_key(cipher_text: str) -> str:
    """
    Decrypt an encrypted API key.
    
    Args:
        cipher_text: The encrypted key
        
    Returns:
        The decrypted plain text key
    """
    return get_fernet().decrypt(cipher_text.encode()).decode()
