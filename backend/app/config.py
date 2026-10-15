import os
import logging
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

logger = logging.getLogger("SocialAgentConfig")

DEV_DEFAULT_FERNET = "k8zZ01Ua9qL_Wc4z7d_YxG8jB2nF6mP0rT3vA5eC7sI="
DEV_DEFAULT_SECRET = "dev_secret_key_change_in_production_min_32_chars!"

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core App Settings
    APP_NAME: str = "AI Social Media Agent"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "sqlite:///./social_agent.db"

    # Security & Encryption
    SECRET_KEY: str = DEV_DEFAULT_SECRET
    FERNET_KEY: str = DEV_DEFAULT_FERNET

    # Mock & Sandbox Modes
    MOCK_SOCIAL_PUBLISHING: bool = True
    SLACK_MOCK_MODE: bool = True

    # LLM Provider Configuration
    # Supported: "gemini", "groq", "mock"
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-flash-lite-latest"
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Legacy/Alternative Providers (Optional)
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # AI Quality & Self-Correction Limits
    AI_QUALITY_THRESHOLD: int = 70
    AI_MAX_CORRECTION_ATTEMPTS: int = 2
    MAX_REGENERATIONS: int = 5

    # Scheduling & Publishing
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_POLL_INTERVAL_SECONDS: int = 15
    MAX_PUBLISH_RETRIES: int = 3
    DEFAULT_TIMEZONE: str = "UTC"

    # Slack Integration
    SLACK_BOT_TOKEN: Optional[str] = None
    SLACK_SIGNING_SECRET: Optional[str] = None
    SLACK_DEFAULT_CHANNEL: str = "#social-approvals"

    # Social Platform OAuth (Optional in dev/mock)
    FRONTEND_ORIGIN: str = "http://localhost:8000"
    X_CLIENT_ID: Optional[str] = None
    X_CLIENT_SECRET: Optional[str] = None
    X_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/twitter/callback"
    LINKEDIN_CLIENT_ID: Optional[str] = None
    LINKEDIN_CLIENT_SECRET: Optional[str] = None
    LINKEDIN_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/linkedin/callback"
    META_APP_ID: Optional[str] = None
    META_APP_SECRET: Optional[str] = None
    META_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/facebook/callback"
    INSTAGRAM_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/instagram/callback"

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        clean = v.lower().strip()
        if clean not in ("development", "production", "test"):
            return "development"
        return clean

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def active_llm_provider(self) -> str:
        """Determines the active LLM provider based on configuration and available API keys.
        Fallback order: Configured Provider -> Alternative Live Provider -> MockProvider.
        """
        requested = (self.LLM_PROVIDER or "mock").lower().strip()
        if requested == "gemini":
            if self.GEMINI_API_KEY and self.GEMINI_API_KEY.strip():
                return "gemini"
            elif self.GROQ_API_KEY and self.GROQ_API_KEY.strip():
                logger.info("Gemini requested but GEMINI_API_KEY missing; falling back to Groq.")
                return "groq"
            else:
                return "mock"
        elif requested == "groq":
            if self.GROQ_API_KEY and self.GROQ_API_KEY.strip():
                return "groq"
            elif self.GEMINI_API_KEY and self.GEMINI_API_KEY.strip():
                logger.info("Groq requested but GROQ_API_KEY missing; falling back to Gemini.")
                return "gemini"
            else:
                return "mock"
        elif requested == "mock":
            return "mock"
        return "mock"

    def validate_production_security(self):
        """Guardrail checking that default development keys are not used in production."""
        if self.is_production:
            if self.FERNET_KEY == DEV_DEFAULT_FERNET:
                raise ValueError("SECURITY ALERT: Cannot use default DEV FERNET_KEY in production mode!")
            if self.SECRET_KEY == DEV_DEFAULT_SECRET or len(self.SECRET_KEY) < 32:
                raise ValueError("SECURITY ALERT: Cannot use default or short SECRET_KEY in production mode!")

settings = Settings()

def get_settings() -> Settings:
    return settings

# Validate guardrails if running in production
if settings.is_production:
    settings.validate_production_security()
