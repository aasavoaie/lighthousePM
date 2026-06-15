import os
from pathlib import Path
from typing import Any

from dotenv import set_key

from app.config import BACKEND_DIR, Settings, get_settings
from app.schemas.configuration import JiraConfigurationResponse, JiraConfigurationUpdate, JiraConnectionTestResponse
from app.services.jira_errors import JiraServiceError
from app.services.jira_service import JiraService

CONFIG_FILE_ENV_VAR = "LIGHTHOUSE_CONFIG_FILE"

JIRA_FIELD_TO_ENV = {
    "jira_base_url": "JIRA_BASE_URL",
    "jira_user_email": "JIRA_USER_EMAIL",
    "jira_api_token": "JIRA_API_TOKEN",
    "jira_project_key": "JIRA_PROJECT_KEY",
    "jira_sync_enabled": "JIRA_SYNC_ENABLED",
    "jira_sync_page_size": "JIRA_SYNC_PAGE_SIZE",
    "jira_sync_changelog_page_size": "JIRA_SYNC_CHANGELOG_PAGE_SIZE",
    "jira_field_story_points": "JIRA_FIELD_STORY_POINTS",
    "jira_field_severity": "JIRA_FIELD_SEVERITY",
    "jira_field_release": "JIRA_FIELD_RELEASE",
    "jira_field_sprint": "JIRA_FIELD_SPRINT",
    "jira_field_blocker": "JIRA_FIELD_BLOCKER",
    "jira_changelog_fix_version_fields": "JIRA_CHANGELOG_FIX_VERSION_FIELDS",
    "jira_changelog_sprint_fields": "JIRA_CHANGELOG_SPRINT_FIELDS",
}


def get_configuration_file_path() -> Path:
    configured_path = os.environ.get(CONFIG_FILE_ENV_VAR)
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return (BACKEND_DIR / ".env").resolve()


def get_jira_configuration() -> JiraConfigurationResponse:
    settings = get_settings()
    return _build_response(settings=settings, config_path=get_configuration_file_path())


def update_jira_configuration(update: JiraConfigurationUpdate) -> JiraConfigurationResponse:
    current_settings = get_settings()
    update_values = update.model_dump(exclude_unset=True)
    normalized_values = _normalize_update_values(update_values)
    candidate_settings = _build_candidate_settings(current_settings, normalized_values)
    candidate_settings.validate_startup_settings()

    config_path = get_configuration_file_path()
    _write_configuration(config_path=config_path, values=normalized_values)
    _apply_runtime_environment(values=normalized_values)
    get_settings.cache_clear()

    return _build_response(settings=get_settings(), config_path=config_path)


def _normalize_update_values(values: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field_name, value in values.items():
        if field_name not in JIRA_FIELD_TO_ENV:
            continue
        if value is None:
            continue
        if field_name in {"jira_sync_page_size", "jira_sync_changelog_page_size"} and int(value) < 1:
            raise ValueError("Jira sync page sizes must be at least 1")
        normalized[field_name] = value.strip() if isinstance(value, str) else value
    return normalized


def _build_candidate_settings(settings: Settings, values: dict[str, Any]) -> Settings:
    candidate_data = settings.model_dump()
    candidate_data.update(values)
    return Settings(_env_file=None, **candidate_data)


def _write_configuration(*, config_path: Path, values: dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.touch(exist_ok=True)
    for field_name, value in values.items():
        if field_name == "jira_api_token":
            continue
        env_name = JIRA_FIELD_TO_ENV[field_name]
        set_key(
            dotenv_path=config_path,
            key_to_set=env_name,
            value_to_set=_to_env_value(value),
            quote_mode="auto",
        )


def _apply_runtime_environment(*, values: dict[str, Any]) -> None:
    for field_name, value in values.items():
        os.environ[JIRA_FIELD_TO_ENV[field_name]] = _to_env_value(value)


def _to_env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _build_response(*, settings: Settings, config_path: Path) -> JiraConfigurationResponse:
    return JiraConfigurationResponse(
        config_path=str(config_path),
        jira_base_url=settings.jira_base_url,
        jira_user_email=settings.jira_user_email,
        jira_api_token_configured=bool(settings.jira_api_token.strip()),
        jira_project_key=settings.jira_project_key,
        jira_sync_enabled=settings.jira_sync_enabled,
        jira_sync_page_size=settings.jira_sync_page_size,
        jira_sync_changelog_page_size=settings.jira_sync_changelog_page_size,
        jira_field_story_points=settings.jira_field_story_points,
        jira_field_severity=settings.jira_field_severity,
        jira_field_release=settings.jira_field_release,
        jira_field_sprint=settings.jira_field_sprint,
        jira_field_blocker=settings.jira_field_blocker,
        jira_changelog_fix_version_fields=settings.jira_changelog_fix_version_fields,
        jira_changelog_sprint_fields=settings.jira_changelog_sprint_fields,
        is_complete=_is_complete(settings),
    )


async def test_jira_connection(update: JiraConfigurationUpdate | None = None) -> JiraConnectionTestResponse:
    current_settings = get_settings()
    update_values = update.model_dump(exclude_unset=True) if update is not None else {}
    normalized_values = _normalize_update_values(update_values)
    candidate_settings = _build_candidate_settings(current_settings, normalized_values)

    try:
        _validate_jira_connection_settings(candidate_settings)
    except ValueError as exc:
        return JiraConnectionTestResponse(ok=False, message=str(exc), project_key=candidate_settings.jira_project_key)

    jira_service = JiraService(settings=candidate_settings)
    try:
        myself = await jira_service.validate_auth()
        versions = await jira_service.get_project_versions(project_key=candidate_settings.jira_project_key.strip())
    except JiraServiceError as exc:
        return JiraConnectionTestResponse(
            ok=False,
            message=str(exc),
            project_key=candidate_settings.jira_project_key.strip() or None,
        )
    finally:
        await jira_service.aclose()

    return JiraConnectionTestResponse(
        ok=True,
        message=f"Connected to Jira and found {len(versions)} releases for project {candidate_settings.jira_project_key.strip()}.",
        account_id=str(myself.get("accountId")) if myself.get("accountId") else None,
        display_name=str(myself.get("displayName")) if myself.get("displayName") else None,
        project_key=candidate_settings.jira_project_key.strip(),
        project_accessible=True,
    )


def _is_complete(settings: Settings) -> bool:
    return all(
        [
            settings.jira_base_url.strip(),
            settings.jira_user_email.strip(),
            settings.jira_api_token.strip(),
            settings.jira_project_key.strip(),
            settings.jira_field_severity.strip(),
            settings.jira_field_release.strip(),
            settings.changelog_fix_version_fields,
        ]
    )


def _validate_jira_connection_settings(settings: Settings) -> None:
    forced_sync_settings = _build_candidate_settings(settings, {"jira_sync_enabled": True})
    forced_sync_settings.validate_startup_settings()
