from functools import cached_property, lru_cache
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.exc import ArgumentError
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE_ENV_VAR = "LIGHTHOUSE_CONFIG_FILE"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
MAX_SECRET_FILE_BYTES = 4096


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "Jira Release Signals"
    app_env: Literal["dev", "test", "prod"] = "dev"
    deployment_mode: Literal["desktop", "local-browser", "docker"] = "local-browser"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/lighthouse"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10
    postgres_password: str = ""
    postgres_password_file: str = ""
    lighthouse_api_token: str = ""
    lighthouse_api_token_file: str = ""

    # Jira Cloud connection
    jira_base_url: str = ""
    jira_user_email: str = ""
    jira_api_token: str = ""
    jira_api_token_file: str = ""
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
    jira_done_statuses: str = "done,closed,resolved"
    jira_in_progress_statuses: str = "in progress,in development,in review,in testing"
    jira_high_severity_values: str = "high,highest,critical"
    jira_bug_issue_types: str = "bug"
    jira_blocker_issue_types: str = "blocker,incident"
    jira_blocker_severity_values: str = "blocker,highest,critical"
    jira_blocked_statuses: str = "blocked"

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

    @property
    def done_statuses(self) -> frozenset[str]:
        return _csv_to_set(self.jira_done_statuses)

    @property
    def in_progress_statuses(self) -> frozenset[str]:
        return _csv_to_set(self.jira_in_progress_statuses)

    @property
    def high_severity_values(self) -> frozenset[str]:
        return _csv_to_set(self.jira_high_severity_values)

    @property
    def bug_issue_types(self) -> frozenset[str]:
        return _csv_to_set(self.jira_bug_issue_types)

    @property
    def blocker_issue_types(self) -> frozenset[str]:
        return _csv_to_set(self.jira_blocker_issue_types)

    @property
    def blocker_severity_values(self) -> frozenset[str]:
        return _csv_to_set(self.jira_blocker_severity_values)

    @property
    def blocked_statuses(self) -> frozenset[str]:
        return _csv_to_set(self.jira_blocked_statuses)

    @property
    def cors_origin_list(self) -> tuple[str, ...]:
        return tuple(origin.strip() for origin in self.cors_origins.split(",") if origin.strip())

    @property
    def is_loopback_binding(self) -> bool:
        return self.app_host.strip().casefold() in LOOPBACK_HOSTS

    @property
    def api_token_required(self) -> bool:
        return (
            self.app_env == "prod"
            or not self.is_loopback_binding
            or self.deployment_mode in {"desktop", "docker"}
        )

    @cached_property
    def effective_lighthouse_api_token(self) -> str:
        return _resolve_secret(
            direct_value=self.lighthouse_api_token,
            file_value=self.lighthouse_api_token_file,
            direct_setting="LIGHTHOUSE_API_TOKEN",
            file_setting="LIGHTHOUSE_API_TOKEN_FILE",
        )

    @cached_property
    def effective_jira_api_token(self) -> str:
        return _resolve_secret(
            direct_value=self.jira_api_token,
            file_value=self.jira_api_token_file,
            direct_setting="JIRA_API_TOKEN",
            file_setting="JIRA_API_TOKEN_FILE",
        )

    @cached_property
    def effective_postgres_password(self) -> str:
        return _resolve_secret(
            direct_value=self.postgres_password,
            file_value=self.postgres_password_file,
            direct_setting="POSTGRES_PASSWORD",
            file_setting="POSTGRES_PASSWORD_FILE",
        )

    @cached_property
    def effective_database_url(self) -> str:
        try:
            database_url = make_url(self.database_url)
        except (ArgumentError, ValueError) as exc:
            raise ValueError("DATABASE_URL must be a valid SQLAlchemy database URL") from exc
        if database_url.get_backend_name() != "postgresql":
            return self.database_url

        external_password = self.effective_postgres_password
        embedded_password = database_url.password
        if embedded_password is not None and external_password:
            raise ValueError(
                "DATABASE_URL and POSTGRES_PASSWORD or POSTGRES_PASSWORD_FILE cannot both "
                "provide the PostgreSQL password"
            )
        if embedded_password is not None and (
            self.app_env == "prod" or self.deployment_mode == "docker"
        ):
            raise ValueError(
                "PostgreSQL passwords must not be embedded in DATABASE_URL in production "
                "or Docker mode"
            )
        if external_password:
            database_url = database_url.set(password=external_password)
        return database_url.render_as_string(hide_password=False)

    @property
    def api_auth_enabled(self) -> bool:
        return bool(self.effective_lighthouse_api_token.strip())

    def validate_deployment_settings(self) -> None:
        """Validate the explicit security boundary for the selected deployment mode."""
        bind_host = self.app_host.strip().casefold()
        if not bind_host:
            raise ValueError("APP_HOST must identify the effective backend bind host")

        for origin in self.cors_origin_list:
            if "*" in origin:
                raise ValueError("CORS_ORIGINS must contain exact origins and cannot use wildcards")
            parsed = urlsplit(origin)
            try:
                parsed.port
            except ValueError as exc:
                raise ValueError("CORS_ORIGINS entries must contain a valid port") from exc
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.hostname is None
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "CORS_ORIGINS entries must be exact HTTP or HTTPS origins without paths, "
                    "credentials, queries, or fragments"
                )

        if self.deployment_mode != "desktop":
            return

        if not self.is_loopback_binding:
            raise ValueError("Desktop deployment requires APP_HOST to be a loopback address")
        if not self.database_url.strip().casefold().startswith(("sqlite://", "sqlite+pysqlite://")):
            raise ValueError("Desktop deployment requires a managed SQLite DATABASE_URL")
        if self.cors_origin_list:
            raise ValueError("Desktop deployment requires CORS_ORIGINS to be empty")

    def validate_api_auth_settings(self) -> None:
        effective_token = self.effective_lighthouse_api_token
        if self.api_token_required and not effective_token.strip():
            raise ValueError(
                "LIGHTHOUSE_API_TOKEN or LIGHTHOUSE_API_TOKEN_FILE is required for the "
                "configured deployment mode, environment, and bind host"
            )

    def validate_secret_settings(self) -> None:
        """Validate configured secret sources even when their integration is disabled."""
        _ = self.effective_lighthouse_api_token
        _ = self.effective_jira_api_token
        _ = self.effective_postgres_password
        _ = self.effective_database_url

    def validate_classification_settings(self) -> None:
        required_sets = {
            "JIRA_DONE_STATUSES": self.done_statuses,
            "JIRA_IN_PROGRESS_STATUSES": self.in_progress_statuses,
            "JIRA_HIGH_SEVERITY_VALUES": self.high_severity_values,
            "JIRA_BUG_ISSUE_TYPES": self.bug_issue_types,
        }
        missing = [name for name, values in required_sets.items() if not values]
        if missing:
            raise ValueError(f"Classification settings must not be empty: {', '.join(missing)}")

        overlapping_statuses = sorted(self.done_statuses & self.in_progress_statuses)
        if overlapping_statuses:
            raise ValueError(
                "JIRA_DONE_STATUSES and JIRA_IN_PROGRESS_STATUSES must not overlap: "
                f"{', '.join(overlapping_statuses)}"
            )

    def validate_startup_settings(self) -> None:
        """Fail fast before migration for deployment, classification, and Jira settings.

        Validation is intentionally scoped to sync-enabled deployments so local
        API-only workflows can run without Jira credentials.
        """
        self.validate_deployment_settings()
        self.validate_secret_settings()
        self.validate_api_auth_settings()
        self.validate_classification_settings()
        if not self.jira_sync_enabled:
            return

        missing: list[str] = []
        if not self.jira_base_url.strip():
            missing.append("JIRA_BASE_URL")
        if not self.jira_user_email.strip():
            missing.append("JIRA_USER_EMAIL")
        if not self.effective_jira_api_token.strip():
            missing.append("JIRA_API_TOKEN or JIRA_API_TOKEN_FILE")
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


def _resolve_secret(
    *,
    direct_value: str,
    file_value: str,
    direct_setting: str,
    file_setting: str,
) -> str:
    secret_file = file_value.strip()
    if direct_value and secret_file:
        raise ValueError(f"{direct_setting} and {file_setting} cannot both be configured")
    if secret_file:
        return _read_secret_file(Path(secret_file), setting_name=file_setting)
    return direct_value


def _read_secret_file(path: Path, *, setting_name: str) -> str:
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{setting_name} must identify a readable regular file")
        size = path.stat().st_size
        if size <= 0 or size > MAX_SECRET_FILE_BYTES:
            raise ValueError(
                f"{setting_name} must contain 1 to {MAX_SECRET_FILE_BYTES} bytes"
            )
        value = path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise ValueError(f"{setting_name} must identify a readable UTF-8 file") from exc
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError(f"{setting_name} must identify a readable UTF-8 file") from exc

    if value.endswith("\r\n"):
        value = value[:-2]
    elif value.endswith(("\r", "\n")):
        value = value[:-1]
    if not value.strip():
        raise ValueError(f"{setting_name} must contain a non-empty secret")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    configured_file = os.environ.get(CONFIG_FILE_ENV_VAR, "").strip()
    env_file = Path(configured_file) if configured_file else BACKEND_DIR / ".env"
    settings = Settings(_env_file=env_file)
    _validate_env_file_secret_sources(settings)
    return settings


def _validate_env_file_secret_sources(settings: Settings) -> None:
    if (
        settings.deployment_mode == "local-browser"
        and settings.app_env in {"dev", "test"}
        and settings.is_loopback_binding
    ):
        return

    direct_secret_settings = {
        "LIGHTHOUSE_API_TOKEN": settings.lighthouse_api_token,
        "JIRA_API_TOKEN": settings.jira_api_token,
        "POSTGRES_PASSWORD": settings.postgres_password,
    }
    file_only_settings = [
        setting_name
        for setting_name, configured_value in direct_secret_settings.items()
        if configured_value and setting_name not in os.environ
    ]
    if file_only_settings:
        raise ValueError(
            "Direct secrets must not be loaded from an environment file in this deployment: "
            f"{', '.join(file_only_settings)}; use the process environment or the corresponding "
            "*_FILE setting"
        )
