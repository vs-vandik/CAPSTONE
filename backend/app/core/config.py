"""Core configuration and settings."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Settings
    API_TITLE: str = "AI Investment Discourse API"
    API_VERSION: str = "0.1.0"
    
    # LLM Settings — DigitalOcean Serverless Inference
    # We use DO as the inference provider via its OpenAI-compatible
    # endpoint. Set MODEL_ACCESS_KEY to a DO model access key from
    # platform.digitalocean.com. LLM_BASE_URL and EMBEDDING_BASE_URL stay
    # configurable so we can swap to OpenAI direct (or any other
    # OpenAI-compatible provider) by changing only .env values.
    MODEL_ACCESS_KEY: Optional[str] = None
    LLM_BASE_URL: str = "https://inference.do-ai.run/v1/"
    LLM_MODEL: str = "anthropic-claude-haiku-4.5"
    EMBEDDING_MODEL: str = "qwen3-embedding-0.6b"
    EMBEDDING_DIM: int = 1024  # qwen3-embedding-0.6b native dim
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 500

    # News grounding (optional). If unset, debates run without current-news context.
    TAVILY_API_KEY: Optional[str] = None
    TAVILY_MAX_RESULTS: int = 5
    
    # Knowledge Base
    DATA_DIR: str = "./data"
    
    # Server Settings
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # CORS
    # CORS_ORIGINS is a comma-separated list of exact origin matches,
    # used for stable URLs like localhost and the production Vercel
    # domain. CORS_ORIGIN_REGEX is a single regex used to match
    # ephemeral preview deployment URLs (Vercel mints a new one for
    # every push, like https://capstone-abc123-capstone26.vercel.app),
    # so we don't have to rotate a Fly secret on every deploy.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    CORS_ORIGIN_REGEX: Optional[str] = None

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS as a comma-separated list of origins.

        We deliberately reject `*` so a development convenience cannot
        accidentally leak to production. Use explicit origins everywhere.
        """
        raw = [o.strip() for o in self.CORS_ORIGINS.split(",")]
        origins = [o for o in raw if o]
        if "*" in origins:
            raise ValueError(
                "CORS_ORIGINS=* is not supported. List explicit origins."
            )
        return origins
    
    # Audio
    ENABLE_TTS: bool = True
    DEFAULT_VOICE: str = "en-US-AriaNeural"
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        # Ignore unknown env vars rather than crashing on them. Useful when
        # an existing .env still has old keys after a rename (e.g.
        # OPENAI_API_KEY -> MODEL_ACCESS_KEY).
        extra = "ignore"


# Global settings instance
settings = Settings()


# Agent configuration constants
AGENT_CONFIG = {
    "max_turns": 6,
    "socratic_mode": True,
    "temperature": 0.7,
    "max_tokens": 500
}