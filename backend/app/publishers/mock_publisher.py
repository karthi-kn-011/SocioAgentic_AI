import uuid
import datetime
from typing import Optional, Any
from .base import BasePublisher, PublishResult

class MockPublisher(BasePublisher):
    """Safe Mock Publisher for simulated publishing during development and testing.

    Never executes external network requests. Explicitly flags all output as simulated.
    """

    def __init__(self, default_failure: bool = False):
        self.default_failure = default_failure

    def publish(self, post: Any, scheduled_post: Optional[Any] = None) -> PublishResult:
        # Prioritize platform on scheduled_post over post.platform
        target_platform = None
        if scheduled_post and getattr(scheduled_post, "target_platforms", None) and len(scheduled_post.target_platforms) > 0:
            target_platform = scheduled_post.target_platforms[0]
        elif scheduled_post and getattr(scheduled_post, "platform", None):
            target_platform = scheduled_post.platform
        elif hasattr(post, "platform"):
            target_platform = post.platform

        platform_str = (
            target_platform.value if hasattr(target_platform, "value") else str(target_platform or "TWITTER")
        ).upper()

        from backend.app.database.models import normalize_platform_name
        platform_name = normalize_platform_name(platform_str, allow_none=True, default_if_none="TWITTER")

        # Extract platform-specific content with strict validation (no cross-platform fallback)
        content = None
        if hasattr(post, "get_platform_content"):
            content = post.get_platform_content(platform_name, strict=True)
        elif hasattr(post, "content") and post.content:
            content = post.content
        elif hasattr(post, "raw_content") and post.raw_content:
            content = post.raw_content

        # Strict validation: Reject missing, empty, or whitespace-only platform content
        if not content or not str(content).strip():
            err_msg = f"Publication rejected: No platform-specific content found for '{platform_name}'. Cross-platform fallback or empty content is strictly prohibited."
            return PublishResult(
                status="FAILED",
                platform=platform_name,
                provider="MockPublisher",
                is_mock=True,
                external_post_id=None,
                response_payload={
                    "simulated": True,
                    "error": err_msg,
                    "simulated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                },
                error_message=err_msg,
            )

        # Check for simulated failure trigger (for testing failure and retry loops)
        should_fail = self.default_failure
        if "[SIMULATE_FAIL]" in content:
            should_fail = True

        if should_fail:
            return PublishResult(
                status="FAILED",
                platform=platform_name,
                provider="MockPublisher",
                is_mock=True,
                external_post_id=None,
                response_payload={
                    "simulated": True,
                    "error": "Simulated platform upstream timeout / rate limit",
                    "simulated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                },
                error_message="Simulated platform connection timeout (503 Service Unavailable)",
            )

        # Generate realistic platform ID
        prefix_map = {
            "TWITTER": "mock_tw",
            "LINKEDIN": "mock_li",
            "INSTAGRAM": "mock_ig",
            "META_INSTAGRAM": "mock_ig",
            "FACEBOOK": "mock_fb",
            "META_FACEBOOK": "mock_fb",
        }
        prefix = prefix_map.get(platform_name, "mock_pub")
        unique_id = uuid.uuid4().hex[:12]
        external_id = f"{prefix}_{unique_id}"

        return PublishResult(
            status="SUCCESS",
            platform=platform_name,
            provider="MockPublisher",
            is_mock=True,
            external_post_id=external_id,
            response_payload={
                "simulated": True,
                "provider": "MockPublisher",
                "platform": platform_name,
                "external_id": external_id,
                "character_count": len(content),
                "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "note": "Simulated publication successful. No external network request was made.",
            },
            error_message=None,
        )
