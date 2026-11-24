import os
import logging
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

logger = logging.getLogger("SocialAgentConfig")

DEV_DEFAULT_FERNET = "k8zZ01Ua9qL_Wc4z7d_YxG8jB2nF6mP0rT3vA5eC7sI="
DEV_DEFAULT_SECRET = "dev_secret_key_change_in_production_min_32_chars!"
DEV_DEFAULT_OPERATOR_USER = "operator"
DEV_DEFAULT_OPERATOR_PASS = "DevSecurePassword2026!"

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

    # Operator Authentication & Access Control
    OPERATOR_USERNAME: str = DEV_DEFAULT_OPERATOR_USER
    OPERATOR_PASSWORD: str = DEV_DEFAULT_OPERATOR_PASS
    API_KEY: Optional[str] = None
    SESSION_MAX_AGE_SECONDS: int = 43200  # 12 hours
    ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

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

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parses comma-separated ALLOWED_ORIGINS into a clean, normalized list."""
        origins = [o.strip().rstrip("/") for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]
        if self.FRONTEND_ORIGIN:
            fe = self.FRONTEND_ORIGIN.strip().rstrip("/")
            if fe and fe not in origins:
                origins.append(fe)
        return origins

    def validate_production_security(self):
        """Guardrail checking that default development keys and credentials are not used in production."""
        if self.is_production:
            if not self.FERNET_KEY or self.FERNET_KEY == DEV_DEFAULT_FERNET:
                raise ValueError("SECURITY ALERT: Cannot use default or empty FERNET_KEY in production mode!")
            try:
                from cryptography.fernet import Fernet
                Fernet(self.FERNET_KEY.encode("utf-8") if isinstance(self.FERNET_KEY, str) else self.FERNET_KEY)
            except Exception as e:
                raise ValueError(f"SECURITY ALERT: Invalid persistent FERNET_KEY format in production: {e}")

            if not self.SECRET_KEY or self.SECRET_KEY == DEV_DEFAULT_SECRET or len(self.SECRET_KEY) < 32:
                raise ValueError("SECURITY ALERT: Cannot use default or short SECRET_KEY (min 32 chars) in production mode!")

            if (
                not self.OPERATOR_USERNAME
                or self.OPERATOR_USERNAME == DEV_DEFAULT_OPERATOR_USER
                or not self.OPERATOR_PASSWORD
                or self.OPERATOR_PASSWORD == DEV_DEFAULT_OPERATOR_PASS
                or len(self.OPERATOR_PASSWORD) < 12
            ):
                raise ValueError(
                    "SECURITY ALERT: Production requires non-default OPERATOR_USERNAME and strong OPERATOR_PASSWORD (min 12 chars)!"
                )

settings = Settings()

def get_settings() -> Settings:
    return settings

# Validate guardrails if running in production
if settings.is_production:
    settings.validate_production_security()
