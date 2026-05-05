"""Core configuration and settings."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Settings
    API_TITLE: str = "AI Investment Discourse API"
    API_VERSION: str = "0.1.0"
    
    # LLM Settings
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gpt-3.5-turbo"
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 500
    
    # Knowledge Base
    DATA_DIR: str = "./data"
    
    # Server Settings
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    
    # Audio
    ENABLE_TTS: bool = True
    DEFAULT_VOICE: str = "en-US-AriaNeural"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()


# Agent configuration constants
AGENT_CONFIG = {
    "max_turns": 6,
    "socratic_mode": True,
    "temperature": 0.7,
    "max_tokens": 500
}