import base64
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from ..config import settings

logger = logging.getLogger("SecurityManager")

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Optional, Dict, Any, List
from fastapi import Request, HTTPException, status
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
            if settings.is_production:
                raise ValueError(f"SECURITY ALERT: Production mode requires a valid persistent FERNET_KEY ({e}).")
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


# ==============================================================================
# Operator Session Management & Cryptographic Signing (HMAC-SHA256)
# ==============================================================================

SESSION_COOKIE_NAME = "operator_session"
CSRF_COOKIE_NAME = "XSRF-TOKEN"
CSRF_HEADER_NAME = "X-CSRF-Token"


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding and padding < 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data.encode("ascii"))


def create_session_token(username: str, ttl_seconds: Optional[int] = None) -> str:
    """Generates an HMAC-SHA256 signed session token for the operator."""
    ttl = ttl_seconds or settings.SESSION_MAX_AGE_SECONDS
    now = int(time.time())
    payload = {
        "sub": username,
        "iat": now,
        "exp": now + ttl,
        "jti": secrets.token_hex(16),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_part = _b64_encode(payload_bytes)

    secret_key = settings.SECRET_KEY.encode("utf-8")
    signature = hmac.new(secret_key, payload_part.encode("ascii"), hashlib.sha256).digest()
    sig_part = _b64_encode(signature)

    return f"{payload_part}.{sig_part}"


def verify_session_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Verifies the HMAC-SHA256 signature and expiration of an operator session token."""
    if not token or "." not in token:
        return None

    try:
        payload_part, sig_part = token.split(".", 1)
        expected_sig = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            payload_part.encode("ascii"),
            hashlib.sha256
        ).digest()

        actual_sig = _b64_decode(sig_part)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload_bytes = _b64_decode(payload_part)
        payload = json.loads(payload_bytes.decode("utf-8"))

        if payload.get("exp", 0) < time.time():
            return None

        return payload
    except Exception:
        return None


def generate_csrf_token() -> str:
    """Generates a random CSRF secret."""
    return secrets.token_urlsafe(32)


# ==============================================================================
# Login Rate Limiting (Sliding Window per IP)
# ==============================================================================

_login_attempts: Dict[str, List[float]] = {}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_RATE_WINDOW_SECONDS = 60.0


def check_login_rate_limit(client_ip: str) -> None:
    """Enforces rate limiting on login attempts to prevent brute force."""
    now = time.time()
    history = _login_attempts.get(client_ip, [])
    # Keep only attempts within the window
    history = [t for t in history if now - t < LOGIN_RATE_WINDOW_SECONDS]
    _login_attempts[client_ip] = history

    if len(history) >= MAX_LOGIN_ATTEMPTS:
        retry_after = int(LOGIN_RATE_WINDOW_SECONDS - (now - history[0])) + 1
        logger.warning("Login rate limit exceeded for client %s (attempts: %s)", client_ip, len(history))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Please retry after {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


def record_failed_login(client_ip: str) -> None:
    """Records a failed login attempt timestamp for client IP."""
    now = time.time()
    history = _login_attempts.get(client_ip, [])
    history.append(now)
    _login_attempts[client_ip] = history


def clear_failed_logins(client_ip: str) -> None:
    """Clears failed login attempts for client IP upon successful login."""
    _login_attempts.pop(client_ip, None)


# ==============================================================================
# Route Protection Dependency
# ==============================================================================

async def verify_operator_session(request: Request) -> Dict[str, Any]:
    """Dependency that verifies that the request is made by an authenticated operator.

    Accepts:
    1. Valid signed HttpOnly 'operator_session' cookie (with CSRF verification for POST/PUT/DELETE/PATCH).
    2. Optional 'X-API-Key' or 'Authorization: Bearer <API_KEY>' for programmatic callers.

    Raises:
    - 401 Unauthorized if unauthenticated or session expired.
    - 403 Forbidden if CSRF token is missing or mismatched on state-changing requests.
    """
    # 1. Check programmatic API Key (if configured)
    api_key_header = request.headers.get("X-API-Key")
    auth_header = request.headers.get("Authorization")
    bearer_token = None
    if auth_header and auth_header.startswith("Bearer "):
        bearer_token = auth_header[7:].strip()

    candidate_key = api_key_header or bearer_token
    if settings.API_KEY and candidate_key:
        if hmac.compare_digest(candidate_key, settings.API_KEY):
            return {"sub": "api_client", "auth_method": "api_key"}

    # 2. Check Operator Session Cookie
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if session_cookie:
        payload = verify_session_token(session_cookie)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or invalid. Please sign in again."
            )

        # Enforce CSRF protection on state-changing methods
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            csrf_header = request.headers.get(CSRF_HEADER_NAME)
            csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
            if not csrf_header or not csrf_cookie or not hmac.compare_digest(csrf_header, csrf_cookie):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF validation failed: missing or invalid CSRF token."
                )

        return payload

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please sign in to access this resource."
    )
