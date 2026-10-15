import base64
import hashlib
import logging
import secrets
import time
from typing import Optional, Tuple
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.database.models import OAuthState, SocialAccount, PlatformType, get_utc_now
from backend.app.auth.security import token_security

logger = logging.getLogger("OAuthService")


class OAuthService:
    """Manages PKCE generation, CSRF state lifecycle, and token persistence."""

    @staticmethod
    def generate_pkce_pair() -> Tuple[str, str]:
        """Generates an RFC 7636 compliant PKCE code_verifier and code_challenge (S256).
        
        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # RFC 7636 specifies a code_verifier must be between 43 and 128 characters
        code_verifier = secrets.token_urlsafe(64)[:128]
        
        # SHA-256 hash followed by URL-safe base64 encoding without padding
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        
        return code_verifier, code_challenge

    @staticmethod
    def generate_state() -> str:
        """Generates a cryptographically secure random state parameter for CSRF protection."""
        return secrets.token_urlsafe(32)

    @classmethod
    def create_oauth_state(
        cls,
        db: Session,
        platform: str,
        code_verifier: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        ttl_seconds: int = 600,
    ) -> OAuthState:
        """Persists a new OAuth state record with expiration timestamp.
        
        Args:
            db: Database session.
            platform: Social platform string (e.g. 'TWITTER').
            code_verifier: Optional PKCE verifier for providers that support PKCE.
            redirect_uri: The redirect URI used in the authorization request.
            ttl_seconds: Time-to-live in seconds (default 10 minutes = 600s).
            
        Returns:
            The created OAuthState model instance.
        """
        state = cls.generate_state()
        expires_at = time.time() + ttl_seconds
        
        record = OAuthState(
            state=state,
            platform=platform.upper(),
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
            expires_at=expires_at,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @classmethod
    def consume_oauth_state(
        cls,
        db: Session,
        state: str,
        expected_platform: str,
        expected_redirect_uri: Optional[str] = None,
    ) -> OAuthState:
        """Atomically validates, deletes, and returns an OAuth state record.
        
        Validates state existence, platform match, redirect URI match, and expiration.
        Immediately deletes the record within a single database transaction to prevent
        state reuse, replay attacks, and race conditions.
        
        Raises:
            HTTPException: 400 Bad Request if invalid, expired, or context mismatched.
        """
        now = time.time()
        
        # Query within an active session transaction
        record = db.query(OAuthState).filter(OAuthState.state == state).first()
        
        if not record:
            logger.warning("OAuth callback received invalid or already consumed state: %s", state)
            raise HTTPException(
                status_code=400,
                detail="Invalid or already consumed OAuth state parameter."
            )
            
        # Verify platform match
        if record.platform.upper() != expected_platform.upper():
            logger.warning(
                "OAuth state platform mismatch. Expected %s, got %s",
                expected_platform, record.platform
            )
            db.delete(record)
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="OAuth state platform mismatch."
            )
            
        # Verify expiration
        if record.expires_at < now:
            logger.warning("OAuth state expired at %s (now: %s)", record.expires_at, now)
            db.delete(record)
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="OAuth state parameter has expired. Please re-authenticate."
            )
            
        # Verify redirect_uri context if provided
        if expected_redirect_uri and record.redirect_uri:
            # Normalize trailing slashes for comparison
            if record.redirect_uri.rstrip("/") != expected_redirect_uri.rstrip("/"):
                logger.warning(
                    "OAuth state redirect URI mismatch. Expected %s, got %s",
                    expected_redirect_uri, record.redirect_uri
                )
                db.delete(record)
                db.commit()
                raise HTTPException(
                    status_code=400,
                    detail="OAuth redirect URI mismatch."
                )
                
        # Detach attributes before deletion
        consumed_state = OAuthState(
            state=record.state,
            platform=record.platform,
            code_verifier=record.code_verifier,
            redirect_uri=record.redirect_uri,
            expires_at=record.expires_at,
        )
        
        # Atomically delete and commit
        db.delete(record)
        db.commit()
        
        logger.info("Successfully validated and consumed OAuth state for %s", expected_platform)
        return consumed_state

    @staticmethod
    def upsert_social_account(
        db: Session,
        platform: PlatformType,
        account_name: str,
        account_id: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        token_expires_at: Optional[any] = None,
    ) -> SocialAccount:
        """Stores or updates credentials for a social account with encrypted tokens at rest.
        
        Args:
            db: Database session.
            platform: PlatformType enum.
            account_name: Display username / handle (e.g. '@brand').
            account_id: Provider unique user/account ID.
            access_token: Plaintext access token (will be encrypted).
            refresh_token: Optional plaintext refresh token (will be encrypted).
            token_expires_at: Optional datetime when access token expires.
            
        Returns:
            The created or updated SocialAccount record.
        """
        encrypted_access = token_security.encrypt(access_token)
        encrypted_refresh = token_security.encrypt(refresh_token) if refresh_token else None
        
        existing = db.query(SocialAccount).filter(
            SocialAccount.platform == platform
        ).first()
        
        now = get_utc_now()
        
        if existing:
            existing.account_name = account_name
            existing.account_id = account_id
            existing.encrypted_access_token = encrypted_access
            existing.encrypted_refresh_token = encrypted_refresh
            existing.token_expires_at = token_expires_at
            existing.is_active = True
            existing.updated_at = now
            db.commit()
            db.refresh(existing)
            logger.info("Updated existing social account #%s for %s (@%s)", existing.id, platform.value, account_name)
            return existing
        else:
            account = SocialAccount(
                platform=platform,
                account_name=account_name,
                account_id=account_id,
                encrypted_access_token=encrypted_access,
                encrypted_refresh_token=encrypted_refresh,
                token_expires_at=token_expires_at,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            db.add(account)
            db.commit()
            db.refresh(account)
            logger.info("Created new social account #%s for %s (@%s)", account.id, platform.value, account_name)
            return account

    @staticmethod
    def disconnect_social_account(db: Session, platform: PlatformType) -> bool:
        """Deactivates and wipes encrypted tokens for a social account.
        
        Returns:
            True if account was found and disconnected, False otherwise.
        """
        account = db.query(SocialAccount).filter(SocialAccount.platform == platform).first()
        if not account:
            return False
            
        account.is_active = False
        account.encrypted_access_token = None
        account.encrypted_refresh_token = None
        account.token_expires_at = None
        account.updated_at = get_utc_now()
        db.commit()
        logger.info("Disconnected social account for %s", platform.value)
        return True
