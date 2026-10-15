from typing import Dict, Type
from .base import BasePublisher
from .mock_publisher import MockPublisher
from backend.app.config import get_settings

class PublisherRegistry:
    """Registry managing available publisher instances for each platform."""

    _publishers: Dict[str, BasePublisher] = {}
    _default_publisher: BasePublisher = MockPublisher()

    @classmethod
    def register(cls, platform: str, publisher: BasePublisher) -> None:
        cls._publishers[platform.upper()] = publisher

    @classmethod
    def get(cls, platform: str) -> BasePublisher:
        if get_settings().MOCK_SOCIAL_PUBLISHING:
            return cls._default_publisher
        platform_key = platform.upper() if platform else "DEFAULT"
        if platform_key == "LINKEDIN" and "LINKEDIN" not in cls._publishers:
            from .linkedin_publisher import LinkedInPublisher
            cls.register("LINKEDIN", LinkedInPublisher())
        elif platform_key == "META_FACEBOOK" and "META_FACEBOOK" not in cls._publishers:
            from .facebook_publisher import FacebookPublisher
            cls.register("META_FACEBOOK", FacebookPublisher())
        elif platform_key == "META_INSTAGRAM" and "META_INSTAGRAM" not in cls._publishers:
            from .instagram_publisher import InstagramPublisher
            cls.register("META_INSTAGRAM", InstagramPublisher())
        return cls._publishers.get(platform_key, cls._default_publisher)

    @classmethod
    def set_default(cls, publisher: BasePublisher) -> None:
        cls._default_publisher = publisher

    @classmethod
    def reset(cls) -> None:
        cls._publishers.clear()
        cls._default_publisher = MockPublisher()

def get_publisher(platform: str) -> BasePublisher:
    return PublisherRegistry.get(platform)
