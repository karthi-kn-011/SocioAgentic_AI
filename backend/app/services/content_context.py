import logging
from typing import Dict, List, Optional
from ..schemas.post import ContentGenerationContext

logger = logging.getLogger("ContentContextService")

class ContentContextService:
    """Constructs enriched multi-factor content generation contexts from user parameters."""

    THEMES = [
        "Thought Leadership",
        "Product Launch",
        "Educational",
        "Storytelling",
        "Promotional",
        "Inspirational",
        "Informative",
        "Announcement",
        "Engagement",
        "Community"
    ]

    TONES = [
        "Professional & Engaging",
        "Visionary & Thought Leadership",
        "Casual & Conversational",
        "Educational & Informative",
        "Energetic & Bold"
    ]

    AUDIENCES = [
        "General Professionals",
        "Tech & Developers",
        "Business & Executives",
        "Creators & Marketers",
        "Students & Learners"
    ]

    @classmethod
    def build_context(
        cls,
        topic: str,
        theme: Optional[str] = "Thought Leadership",
        platforms: Optional[List[str]] = None,
        tone: Optional[str] = "Professional & Engaging",
        target_audience: Optional[str] = "General Professionals",
        content_type: Optional[str] = "Quick Insight",
        desired_length: Optional[str] = "Medium",
        keywords: Optional[List[str]] = None,
        cta_preference: Optional[str] = None,
        previous_content: Optional[Dict[str, str]] = None,
        variation_index: int = 0
    ) -> ContentGenerationContext:
        """Assembles a validated ContentGenerationContext ensuring rich parameters for LLM generation."""
        clean_topic = topic.strip()
        clean_theme = theme.strip() if theme and theme.strip() in cls.THEMES else "Thought Leadership"
        clean_platforms = platforms if platforms else ["TWITTER", "LINKEDIN", "META_FACEBOOK", "META_INSTAGRAM"]
        clean_tone = tone.strip() if tone else "Professional & Engaging"
        clean_audience = target_audience.strip() if target_audience else "General Professionals"

        context = ContentGenerationContext(
            topic=clean_topic,
            theme=clean_theme,
            platforms=clean_platforms,
            tone=clean_tone,
            target_audience=clean_audience,
            content_type=content_type or "Quick Insight",
            desired_length=desired_length or "Medium",
            keywords=keywords or [],
            cta_preference=cta_preference,
            previous_content=previous_content,
            variation_index=variation_index
        )
        return context

content_context_service = ContentContextService()
