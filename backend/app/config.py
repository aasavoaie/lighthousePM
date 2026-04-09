from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "Jira Release Signals"
    app_env: Literal["dev", "test", "prod"] = "dev"
    app_port: int = 8000
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/lighthouse"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # Jira Cloud connection
    jira_base_url: str = ""
    jira_user_email: str = ""
    jira_api_token: str = ""
    jira_timeout_seconds: float = 30.0
    jira_max_retries: int = 2
    jira_project_key: str = ""
    jira_sync_enabled: bool = True
    jira_sync_page_size: int = 50
    jira_sync_changelog_page_size: int = 100
    jira_sync_interval_seconds: int = 0  # 0 = scheduler disabled

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
