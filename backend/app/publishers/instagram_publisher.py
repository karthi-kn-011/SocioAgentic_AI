import logging
from typing import Optional, Any
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.database.database import SessionLocal
from backend.app.database.models import PlatformType, SocialAccount, get_utc_now
from backend.app.auth.security import token_security
from backend.app.auth.instagram_oauth import InstagramOAuthService
from .base import BasePublisher, PublishResult
from .mock_publisher import MockPublisher

logger = logging.getLogger("InstagramPublisher")


class InstagramPublisher(BasePublisher):
    """Live Meta Instagram Business Publisher implementing the Graph API v21.0 Container Workflow.
    
    Strict Media Rule: Rejects text-only posts and missing/invalid public image/video URLs.
    Safe Fail-Safe Guardrail: When MOCK_SOCIAL_PUBLISHING is True, delegates
    strictly to MockPublisher to prevent accidental live publication.
    """

    def publish(self, post: Any, scheduled_post: Optional[Any] = None, db: Optional[Session] = None) -> PublishResult:
        settings = get_settings()

        # Strict Mock Mode Guardrail
        if settings.MOCK_SOCIAL_PUBLISHING:
            logger.info("MOCK_SOCIAL_PUBLISHING is True; delegating Instagram publication to MockPublisher.")
            return MockPublisher().publish(post=post, scheduled_post=scheduled_post)

        # 1. Extract Media URL (Instagram strictly requires media)
        media_url = None
        if hasattr(post, "media_url") and post.media_url:
            media_url = post.media_url
        elif hasattr(post, "image_url") and post.image_url:
            media_url = post.image_url
        elif hasattr(post, "platform_contents") and isinstance(post.platform_contents, dict):
            ig_content = post.platform_contents.get("META_INSTAGRAM") or post.platform_contents.get("INSTAGRAM")
            if isinstance(ig_content, dict):
                media_url = ig_content.get("media_url") or ig_content.get("image_url")

        # 2. Enforce Media Validation: Reject text-only posts immediately
        is_valid_media, media_err = InstagramOAuthService.validate_media_url(media_url)
        if not is_valid_media:
            logger.warning("Instagram publishing rejected due to missing/invalid media: %s", media_err)
            return PublishResult(
                status="FAILED",
                platform="META_INSTAGRAM",
                provider="InstagramPublisher",
                is_mock=False,
                error_message=media_err,
            )

        # 3. Extract platform caption
        caption = None
        if hasattr(post, "get_platform_content"):
            caption = post.get_platform_content("META_INSTAGRAM", strict=True)
        elif hasattr(post, "content") and post.content:
            caption = post.content
        elif hasattr(post, "raw_content") and post.raw_content:
            caption = post.raw_content

        # 4. Retrieve connected Instagram Business account
        db_created = False
        if db is None:
            db = SessionLocal()
            db_created = True
        try:
            account = db.query(SocialAccount).filter(
                SocialAccount.platform == PlatformType.META_INSTAGRAM,
                SocialAccount.is_active == True,
            ).first()

            if not account or not account.encrypted_access_token:
                err = "Instagram publication rejected: No active connected Instagram Business account found. Connect account in Settings."
                return PublishResult(
                    status="FAILED",
                    platform="META_INSTAGRAM",
                    provider="InstagramPublisher",
                    is_mock=False,
                    error_message=err,
                )

            # Check expiration
            now = get_utc_now()
            if account.token_expires_at and account.token_expires_at < now:
                err = "Instagram publication rejected: Page access token for Instagram has expired. Please re-authenticate."
                return PublishResult(
                    status="FAILED",
                    platform="META_INSTAGRAM",
                    provider="InstagramPublisher",
                    is_mock=False,
                    error_message=err,
                )

            # Decrypt Page access token
            page_token = token_security.decrypt(account.encrypted_access_token)
            if not page_token:
                err = "Instagram publication rejected: Failed to decrypt access token."
                return PublishResult(
                    status="FAILED",
                    platform="META_INSTAGRAM",
                    provider="InstagramPublisher",
                    is_mock=False,
                    error_message=err,
                )

            ig_user_id = account.account_id
            if not ig_user_id:
                err = "Instagram publication rejected: Missing Instagram User ID."
                return PublishResult(
                    status="FAILED",
                    platform="META_INSTAGRAM",
                    provider="InstagramPublisher",
                    is_mock=False,
                    error_message=err,
                )

            # 5. Step 1: Create Media Container
            try:
                creation_id = InstagramOAuthService.create_media_container(
                    ig_user_id=ig_user_id,
                    image_url=media_url,
                    caption=caption,
                    page_access_token=page_token,
                )
            except Exception as exc:
                logger.error("Failed to create Instagram media container: %s", exc)
                return PublishResult(
                    status="FAILED",
                    platform="META_INSTAGRAM",
                    provider="InstagramPublisher",
                    is_mock=False,
                    error_message=f"Failed to create Instagram media container: {str(exc)}",
                )

            # 6. Step 2: Check Container Processing Status
            container_status = InstagramOAuthService.check_container_status(
                creation_id=creation_id,
                page_access_token=page_token,
            )
            status_code = container_status.get("status_code", "FINISHED")
            if status_code in ("ERROR", "EXPIRED"):
                err = f"Instagram container processing failed with status '{status_code}'."
                return PublishResult(
                    status="FAILED",
                    platform="META_INSTAGRAM",
                    provider="InstagramPublisher",
                    is_mock=False,
                    error_message=err,
                    response_payload=container_status,
                )

            # 7. Step 3: Publish Container
            try:
                ig_media_id = InstagramOAuthService.publish_media_container(
                    ig_user_id=ig_user_id,
                    creation_id=creation_id,
                    page_access_token=page_token,
                )
                return PublishResult(
                    status="SUCCESS",
                    platform="META_INSTAGRAM",
                    provider="InstagramPublisher",
                    is_mock=False,
                    external_post_id=ig_media_id,
                    response_payload={"creation_id": creation_id, "media_id": ig_media_id},
                )
            except Exception as exc:
                logger.error("Failed to publish Instagram media container: %s", exc)
                return PublishResult(
                    status="FAILED",
                    platform="META_INSTAGRAM",
                    provider="InstagramPublisher",
                    is_mock=False,
                    error_message=f"Failed to publish Instagram container: {str(exc)}",
                )
        finally:
            if db_created:
                db.close()
