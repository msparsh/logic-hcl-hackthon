"""Application settings, loaded from environment variables or the .env file.

Every value has a safe default so the app starts without a .env file.
Secrets (API keys, database URL) are never hard-coded in source code.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings. Environment variable names are the upper-case field names."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"

    # --- Database -----------------------------------------------------------
    database_url: str = "postgresql://postgres:postgres@localhost:5432/logic"
    test_database_url: str = ""
    db_echo: bool = False  # log every SQL statement (debugging only)

    # --- LLM providers (tried in this order; empty key = provider skipped) ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: str = "low"  # low effort keeps replies fast for chat

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_url: str = "https://api.groq.com/openai/v1/chat/completions"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    pollinations_enabled: bool = True  # keyless backup provider
    pollinations_model: str = "openai"
    pollinations_url: str = "https://text.pollinations.ai/openai"

    llm_timeout_seconds: float = 8.0

    # --- Agent behaviour (docs/BUSINESS_RULES.md) ---------------------------
    intent_confidence_threshold: float = 0.70  # R11
    preview_ttl_minutes: int = 5  # R9


@lru_cache
def get_settings() -> Settings:
    """Return the settings, read once per process."""
    return Settings()
