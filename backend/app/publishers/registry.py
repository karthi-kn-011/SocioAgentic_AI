from typing import Dict, Type
from .base import BasePublisher
from .mock_publisher import MockPublisher

class PublisherRegistry:
    """Registry managing available publisher instances for each platform."""

    _publishers: Dict[str, BasePublisher] = {}
    _default_publisher: BasePublisher = MockPublisher()

    @classmethod
    def register(cls, platform: str, publisher: BasePublisher) -> None:
        cls._publishers[platform.upper()] = publisher

    @classmethod
    def get(cls, platform: str) -> BasePublisher:
        platform_key = platform.upper() if platform else "DEFAULT"
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
