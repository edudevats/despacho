"""
Cryptographic utilities for secure password/data encryption.

Security: Encryption key MUST be provided via FERNET_KEY environment variable.
Generate a key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from cryptography.fernet import Fernet, InvalidToken
import os
import logging

logger = logging.getLogger(__name__)


class CryptoKeyError(Exception):
    """Raised when encryption key is missing or invalid."""
    pass


def generate_key() -> str:
    """
    Generate a new Fernet encryption key.
    
    Returns:
        str: Base64-encoded Fernet key (safe to store in env variable)
    
    Usage:
        key = generate_key()
        print(f"Add to .env: FERNET_KEY={key}")
    """
    return Fernet.generate_key().decode()


def load_key() -> bytes:
    """
    Load encryption key from environment variable.
    
    Returns:
        bytes: Fernet-compatible encryption key
        
    Raises:
        CryptoKeyError: If FERNET_KEY is not set or invalid
    """
    key = os.environ.get('FERNET_KEY')
    
    if not key:
        # Check for legacy file-based key (migration support)
        legacy_path = os.path.join(os.path.dirname(__file__), '..', 'secret.key')
        if os.path.exists(legacy_path):
            logger.warning(
                "Using legacy secret.key file. Please migrate to FERNET_KEY environment variable."
            )
            with open(legacy_path, 'rb') as f:
                return f.read()
        
        raise CryptoKeyError(
            "FERNET_KEY environment variable not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    
    # Handle both string and bytes
    return key.encode() if isinstance(key, str) else key


def encrypt_password(password: str) -> str:
    """
    Encrypt a password using Fernet symmetric encryption.
    
    Args:
        password: Plain text password to encrypt
        
    Returns:
        str: Encrypted password (base64 encoded)
        
    Raises:
        CryptoKeyError: If encryption key is not available
    """
    try:
        key = load_key()
        f = Fernet(key)
        return f.encrypt(password.encode()).decode()
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise


def decrypt_password(encrypted_password: str) -> str:
    """
    Decrypt a password using Fernet symmetric encryption.
    
    Args:
        encrypted_password: Encrypted password (base64 encoded)
        
    Returns:
        str: Decrypted plain text password
        
    Raises:
        CryptoKeyError: If encryption key is not available
        InvalidToken: If decryption fails (wrong key or corrupted data)
    """
    try:
        key = load_key()
        f = Fernet(key)
        return f.decrypt(encrypted_password.encode()).decode()
    except InvalidToken:
        logger.error("Decryption failed: Invalid token (wrong key or corrupted data)")
        raise
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise
