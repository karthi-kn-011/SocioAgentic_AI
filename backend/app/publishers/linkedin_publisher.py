import logging
from typing import Optional, Any
import httpx
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.database.database import SessionLocal
from backend.app.database.models import PlatformType, SocialAccount, get_utc_now
from backend.app.auth.security import token_security
from backend.app.auth.linkedin_oauth import LinkedInOAuthService, LINKEDIN_POSTS_URL
from .base import BasePublisher, PublishResult
from .mock_publisher import MockPublisher

logger = logging.getLogger("LinkedInPublisher")


class LinkedInPublisher(BasePublisher):
    """Live LinkedIn Publisher implementing the LinkedIn Posts REST API.
    
    Safe Fail-Safe Guardrail: When MOCK_SOCIAL_PUBLISHING is True, delegates
    strictly to MockPublisher to prevent accidental live publication.
    """

    def publish(self, post: Any, scheduled_post: Optional[Any] = None) -> PublishResult:
        settings = get_settings()

        # Strict Mock Mode Guardrail
        if settings.MOCK_SOCIAL_PUBLISHING:
            logger.info("MOCK_SOCIAL_PUBLISHING is True; delegating LinkedIn publication to MockPublisher.")
            return MockPublisher().publish(post=post, scheduled_post=scheduled_post)

        # Extract platform content
        content = None
        if hasattr(post, "get_platform_content"):
            content = post.get_platform_content("LINKEDIN", strict=True)
        elif hasattr(post, "content") and post.content:
            content = post.content
        elif hasattr(post, "raw_content") and post.raw_content:
            content = post.raw_content

        if not content or not str(content).strip():
            err = "LinkedIn publication rejected: Missing or empty platform content for LINKEDIN."
            return PublishResult(
                status="FAILED",
                platform="LINKEDIN",
                provider="LinkedInPublisher",
                is_mock=False,
                error_message=err,
            )

        # Retrieve connected LinkedIn account
        db: Session = SessionLocal()
        try:
            account = db.query(SocialAccount).filter(
                SocialAccount.platform == PlatformType.LINKEDIN,
                SocialAccount.is_active == True,
            ).first()

            if not account or not account.encrypted_access_token:
                err = "LinkedIn publication rejected: No active connected LinkedIn account found. Connect account in Settings."
                return PublishResult(
                    status="FAILED",
                    platform="LINKEDIN",
                    provider="LinkedInPublisher",
                    is_mock=False,
                    error_message=err,
                )

            # Check expiration
            now = get_utc_now()
            if account.token_expires_at and account.token_expires_at < now:
                err = "LinkedIn publication rejected: Access token has expired. Please re-authenticate."
                return PublishResult(
                    status="FAILED",
                    platform="LINKEDIN",
                    provider="LinkedInPublisher",
                    is_mock=False,
                    error_message=err,
                )

            # Decrypt access token
            access_token = token_security.decrypt(account.encrypted_access_token)
            if not access_token:
                err = "LinkedIn publication rejected: Failed to decrypt access token."
                return PublishResult(
                    status="FAILED",
                    platform="LINKEDIN",
                    provider="LinkedInPublisher",
                    is_mock=False,
                    error_message=err,
                )

            author_urn = account.account_id or "urn:li:person:unknown"
            payload = LinkedInOAuthService.format_post_payload(author_urn=author_urn, commentary=content)

            headers = {
                "Authorization": f"Bearer {access_token}",
                "LinkedIn-Version": "202401",
                "X-Restli-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
            }

            try:
                with httpx.Client(timeout=20.0) as client:
                    resp = client.post(LINKEDIN_POSTS_URL, json=payload, headers=headers)
                    if resp.status_code in (200, 201):
                        external_id = resp.headers.get("x-restli-id") or resp.headers.get("X-RestLi-Id")
                        resp_data = resp.json() if resp.text else {}
                        return PublishResult(
                            status="SUCCESS",
                            platform="LINKEDIN",
                            provider="LinkedInPublisher",
                            is_mock=False,
                            external_post_id=external_id or resp_data.get("id"),
                            response_payload=resp_data,
                        )
                    else:
                        logger.error("LinkedIn Posts API returned error (%s): %s", resp.status_code, resp.text)
                        return PublishResult(
                            status="FAILED",
                            platform="LINKEDIN",
                            provider="LinkedInPublisher",
                            is_mock=False,
                            error_message=f"LinkedIn API error ({resp.status_code}): {resp.text}",
                        )
            except httpx.RequestError as exc:
                logger.exception("HTTP error during LinkedIn publication: %s", exc)
                return PublishResult(
                    status="FAILED",
                    platform="LINKEDIN",
                    provider="LinkedInPublisher",
                    is_mock=False,
                    error_message=f"Network error communicating with LinkedIn Posts API: {str(exc)}",
                )
        finally:
            db.close()
