"""Application configuration from environment variables."""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Server
    app_name: str = "Incident Autopilot"
    debug: bool = False

    # Webhook Security
    autopilot_webhook_secret: str = Field(default="change-me-in-production")

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # LLM Provider
    llm_provider: str = Field(default="openai")  # "openai" or "anthropic"
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o")
    anthropic_api_key: str = Field(default="")
    anthropic_model: str = Field(default="claude-sonnet-4-20250514")

    # Jira
    jira_base_url: str = Field(default="https://your-domain.atlassian.net")
    jira_email: str = Field(default="")
    jira_api_token: str = Field(default="")

    # Slack
    slack_bot_token: str = Field(default="")
    slack_channel: str = Field(default="#incidents")

    # Database
    database_url: str = Field(default="sqlite:///./data/audit.db")
    audit_jsonl_path: str = Field(default="./data/audit.jsonl")

    # Feature Flags
    dry_run: bool = Field(default=False)

    # Correlation
    correlation_window_minutes: int = 30

    # Timeouts (seconds)
    http_timeout: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
