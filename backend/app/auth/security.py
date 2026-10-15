import base64
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from ..config import settings

logger = logging.getLogger("SecurityManager")

class TokenSecurity:
    """Manages symmetric encryption and decryption of OAuth tokens at rest using Fernet."""

    def __init__(self, key: Optional[str] = None):
        raw_key = key or settings.FERNET_KEY
        try:
            # Ensure valid Fernet key formatting
            self._fernet = Fernet(raw_key.encode("utf-8") if isinstance(raw_key, str) else raw_key)
        except Exception as e:
            logger.warning(f"Invalid Fernet key supplied ({e}). Generating fallback key for current session.")
            self._fernet = Fernet(Fernet.generate_key())

    def encrypt(self, plain_text: Optional[str]) -> Optional[str]:
        """Encrypts plaintext string to URL-safe base64 token string."""
        if plain_text is None:
            return None
        if not plain_text:
            return ""
        try:
            encrypted_bytes = self._fernet.encrypt(plain_text.encode("utf-8"))
            return encrypted_bytes.decode("utf-8")
        except Exception as e:
            logger.error(f"Token encryption failed: {e}")
            raise ValueError("Failed to encrypt token data.")

    def decrypt(self, cipher_text: Optional[str]) -> Optional[str]:
        """Decrypts ciphertext string back to plaintext."""
        if cipher_text is None:
            return None
        if not cipher_text:
            return ""
        try:
            decrypted_bytes = self._fernet.decrypt(cipher_text.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken:
            logger.error("Token decryption failed: Invalid token or key mismatch.")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during token decryption: {e}")
            return None

token_security = TokenSecurity()
