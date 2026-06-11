from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "Jira Release Signals"
    app_env: Literal["dev", "test", "prod"] = "dev"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
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
    jira_sync_enabled: bool = False
    jira_sync_page_size: int = 50
    jira_sync_changelog_page_size: int = 100
    jira_sync_interval_seconds: int = 0  # 0 = scheduler disabled

    # Jira field mapping overrides (explicit per-instance mapping)
    jira_field_story_points: str = ""
    jira_field_severity: str = "priority"
    jira_field_release: str = "fixVersions"
    jira_field_sprint: str = ""
    jira_field_blocker: str = ""
    jira_blocker_true_values: str = "true,yes,1,blocker"
    jira_changelog_fix_version_fields: str = "fix version,fixversion"
    jira_changelog_sprint_fields: str = "sprint"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator(
        "jira_field_severity",
        "jira_field_release",
        "jira_changelog_fix_version_fields",
        mode="before",
    )
    @classmethod
    def _strip_required_mapping_values(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @property
    def blocker_true_values(self) -> frozenset[str]:
        return _csv_to_set(self.jira_blocker_true_values)

    @property
    def changelog_fix_version_fields(self) -> frozenset[str]:
        return _csv_to_set(self.jira_changelog_fix_version_fields)

    @property
    def changelog_sprint_fields(self) -> frozenset[str]:
        return _csv_to_set(self.jira_changelog_sprint_fields)

    def validate_startup_settings(self) -> None:
        """Fail-fast validation for required Jira sync settings.

        Validation is intentionally scoped to sync-enabled deployments so local
        API-only workflows can run without Jira credentials.
        """
        if not self.jira_sync_enabled:
            return

        missing: list[str] = []
        if not self.jira_base_url.strip():
            missing.append("JIRA_BASE_URL")
        if not self.jira_user_email.strip():
            missing.append("JIRA_USER_EMAIL")
        if not self.jira_api_token.strip():
            missing.append("JIRA_API_TOKEN")
        if not self.jira_project_key.strip():
            missing.append("JIRA_PROJECT_KEY")
        if not self.jira_field_severity.strip():
            missing.append("JIRA_FIELD_SEVERITY")
        if not self.jira_field_release.strip():
            missing.append("JIRA_FIELD_RELEASE")
        if not self.changelog_fix_version_fields:
            missing.append("JIRA_CHANGELOG_FIX_VERSION_FIELDS")

        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Missing required Jira startup settings: {joined}")

        if not self.jira_base_url.startswith(("http://", "https://")):
            raise ValueError("JIRA_BASE_URL must start with http:// or https://")


def _csv_to_set(value: str) -> frozenset[str]:
    return frozenset(item.strip().casefold() for item in value.split(",") if item.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
