from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class PublishResult(BaseModel):
    status: str = Field(..., description="Publication status: SUCCESS, FAILED, SIMULATED")
    platform: str = Field(..., description="Social platform name")
    provider: str = Field(default="MockPublisher", description="Publisher implementation name")
    is_mock: bool = Field(default=True, description="Flag indicating if the publish operation was simulated")
    external_post_id: Optional[str] = Field(default=None, description="External platform post ID or simulated ID")
    response_payload: Optional[Dict[str, Any]] = Field(default=None, description="Raw or simulated platform response")
    error_message: Optional[str] = Field(default=None, description="Error message if publish failed")

class BasePublisher(ABC):
    """Abstract base class for all platform publisher implementations."""

    @abstractmethod
    def publish(self, post: Any, scheduled_post: Optional[Any] = None) -> PublishResult:
        """Publish a post to the designated platform.

        Args:
            post: The Post model instance containing content, media, platform, etc.
            scheduled_post: The ScheduledPost model instance if published via schedule.

        Returns:
            PublishResult containing the status, external ID, and payload.
        """
        pass
