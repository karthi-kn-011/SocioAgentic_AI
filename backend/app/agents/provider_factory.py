import logging
from typing import Optional
from ..config import settings
from .base_provider import BaseLLMProvider
from .gemini_provider import GeminiProvider
from .groq_provider import GroqProvider
from .mock_provider import MockProvider

logger = logging.getLogger("LLMProviderFactory")

class LLMProviderFactory:
    """Factory creating and resolving active LLM providers with automatic fallback cascade:
    User Choice -> Configured Provider -> Alternative Live Provider -> Contextual MockProvider.
    """

    @classmethod
    def get_provider(cls, override_name: Optional[str] = None) -> BaseLLMProvider:
        requested = (override_name or settings.LLM_PROVIDER or "auto").lower().strip()

        # 1. Auto selection (selects best available live provider)
        if requested in ("auto", "best"):
            groq = GroqProvider()
            if groq.is_available():
                logger.info("Active LLM Provider: Groq (Auto-Selected)")
                return groq
            gemini = GeminiProvider()
            if gemini.is_available():
                logger.info("Active LLM Provider: Google Gemini (Auto-Selected)")
                return gemini
            logger.info("No live LLM API keys detected. Falling back to Context-Aware MockProvider.")
            return MockProvider()

        # 2. Try Gemini if requested
        elif requested == "gemini":
            gemini = GeminiProvider()
            if gemini.is_available():
                logger.info("Active LLM Provider: Google Gemini")
                return gemini
            logger.warning("Gemini requested but GEMINI_API_KEY is not set. Checking Groq fallback...")
            groq = GroqProvider()
            if groq.is_available():
                logger.info("Active LLM Provider: Groq (Fallback from Gemini)")
                return groq
            logger.info("No live LLM API keys detected. Falling back to Context-Aware MockProvider.")
            return MockProvider()

        # 3. Try Groq if requested
        elif requested == "groq":
            groq = GroqProvider()
            if groq.is_available():
                logger.info("Active LLM Provider: Groq Cloud")
                return groq
            logger.warning("Groq requested but GROQ_API_KEY is not set. Checking Gemini fallback...")
            gemini = GeminiProvider()
            if gemini.is_available():
                logger.info("Active LLM Provider: Google Gemini (Fallback from Groq)")
                return gemini
            logger.info("No live LLM API keys detected. Falling back to Context-Aware MockProvider.")
            return MockProvider()

        # 4. Explicit Mock or fallback
        else:
            logger.info("Active LLM Provider: MockProvider (Configured)")
            return MockProvider()

# Global factory helper
get_llm_provider = LLMProviderFactory.get_provider
