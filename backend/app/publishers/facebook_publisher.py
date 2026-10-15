import logging
from typing import Optional, Any
import httpx
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.database.database import SessionLocal
from backend.app.database.models import PlatformType, SocialAccount, get_utc_now
from backend.app.auth.security import token_security
from backend.app.auth.facebook_oauth import GRAPH_API_VERSION
from .base import BasePublisher, PublishResult
from .mock_publisher import MockPublisher

logger = logging.getLogger("FacebookPublisher")


class FacebookPublisher(BasePublisher):
    """Live Meta Facebook Page Publisher implementing the Graph API v21.0 Page Feed endpoint.
    
    Safe Fail-Safe Guardrail: When MOCK_SOCIAL_PUBLISHING is True, delegates
    strictly to MockPublisher to prevent accidental live publication.
    """

    def publish(self, post: Any, scheduled_post: Optional[Any] = None) -> PublishResult:
        settings = get_settings()

        # Strict Mock Mode Guardrail
        if settings.MOCK_SOCIAL_PUBLISHING:
            logger.info("MOCK_SOCIAL_PUBLISHING is True; delegating Facebook publication to MockPublisher.")
            return MockPublisher().publish(post=post, scheduled_post=scheduled_post)

        # Extract platform content
        content = None
        if hasattr(post, "get_platform_content"):
            content = post.get_platform_content("META_FACEBOOK", strict=True)
        elif hasattr(post, "content") and post.content:
            content = post.content
        elif hasattr(post, "raw_content") and post.raw_content:
            content = post.raw_content

        if not content or not str(content).strip():
            err = "Facebook Page publication rejected: Missing or empty platform content for META_FACEBOOK."
            return PublishResult(
                status="FAILED",
                platform="META_FACEBOOK",
                provider="FacebookPublisher",
                is_mock=False,
                error_message=err,
            )

        # Retrieve connected Facebook Page account
        db: Session = SessionLocal()
        try:
            account = db.query(SocialAccount).filter(
                SocialAccount.platform == PlatformType.META_FACEBOOK,
                SocialAccount.is_active == True,
            ).first()

            if not account or not account.encrypted_access_token:
                err = "Facebook Page publication rejected: No active connected Facebook Page found. Connect account in Settings."
                return PublishResult(
                    status="FAILED",
                    platform="META_FACEBOOK",
                    provider="FacebookPublisher",
                    is_mock=False,
                    error_message=err,
                )

            # Check expiration
            now = get_utc_now()
            if account.token_expires_at and account.token_expires_at < now:
                err = "Facebook Page publication rejected: Page access token has expired. Please re-authenticate."
                return PublishResult(
                    status="FAILED",
                    platform="META_FACEBOOK",
                    provider="FacebookPublisher",
                    is_mock=False,
                    error_message=err,
                )

            # Decrypt Page access token
            page_token = token_security.decrypt(account.encrypted_access_token)
            if not page_token:
                err = "Facebook Page publication rejected: Failed to decrypt Page access token."
                return PublishResult(
                    status="FAILED",
                    platform="META_FACEBOOK",
                    provider="FacebookPublisher",
                    is_mock=False,
                    error_message=err,
                )

            page_id = account.account_id
            if not page_id:
                err = "Facebook Page publication rejected: Missing Facebook Page ID."
                return PublishResult(
                    status="FAILED",
                    platform="META_FACEBOOK",
                    provider="FacebookPublisher",
                    is_mock=False,
                    error_message=err,
                )

            feed_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/feed"
            payload = {
                "message": content,
                "access_token": page_token,
            }

            try:
                with httpx.Client(timeout=20.0) as client:
                    resp = client.post(feed_url, data=payload)
                    if resp.status_code in (200, 201):
                        resp_data = resp.json() if resp.text else {}
                        post_id = resp_data.get("id")
                        return PublishResult(
                            status="SUCCESS",
                            platform="META_FACEBOOK",
                            provider="FacebookPublisher",
                            is_mock=False,
                            external_post_id=post_id,
                            response_payload=resp_data,
                        )
                    else:
                        logger.error("Meta Graph API returned error (%s): %s", resp.status_code, resp.text)
                        return PublishResult(
                            status="FAILED",
                            platform="META_FACEBOOK",
                            provider="FacebookPublisher",
                            is_mock=False,
                            error_message=f"Meta Graph API error ({resp.status_code}): {resp.text}",
                        )
            except httpx.RequestError as exc:
                logger.exception("HTTP error during Facebook Page publication: %s", exc)
                return PublishResult(
                    status="FAILED",
                    platform="META_FACEBOOK",
                    provider="FacebookPublisher",
                    is_mock=False,
                    error_message=f"Network error communicating with Meta Graph API: {str(exc)}",
                )
        finally:
            db.close()
