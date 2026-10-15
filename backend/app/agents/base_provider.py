from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ..schemas.post import ContentGenerationContext, PostVariant, QualityRubricResult

class BaseLLMProvider(ABC):
    """Abstract base class defining the contract for all AI LLM providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the unique name identifier of the provider (e.g., 'gemini', 'groq', 'mock')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Checks whether the provider is configured and ready for generation."""
        pass

    @abstractmethod
    async def generate_variants(self, context: ContentGenerationContext) -> Dict[str, PostVariant]:
        """Generates platform-tailored post variants based on the rich context."""
        pass

    @abstractmethod
    async def evaluate_quality(
        self,
        variants: Dict[str, str],
        context: ContentGenerationContext
    ) -> QualityRubricResult:
        """Evaluates content quality across grammar, topic relevance, theme adherence, and platform rules."""
        pass
