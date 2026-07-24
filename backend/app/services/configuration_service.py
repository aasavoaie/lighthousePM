import os
from pathlib import Path
import re
import tempfile
from typing import Any

from app.config import BACKEND_DIR, CONFIG_FILE_ENV_VAR, Settings, get_settings
from app.schemas.configuration import JiraConfigurationResponse, JiraConfigurationUpdate, JiraConnectionTestResponse
from app.services.jira_errors import JiraServiceError
from app.services.jira_service import JiraService

_ENV_ASSIGNMENT = re.compile(r"^(?P<prefix>\s*(?:export\s+)?)(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=")

JIRA_FIELD_TO_ENV = {
    "jira_base_url": "JIRA_BASE_URL",
    "jira_user_email": "JIRA_USER_EMAIL",
    "jira_api_token": "JIRA_API_TOKEN",
    "jira_project_key": "JIRA_PROJECT_KEY",
    "jira_sync_enabled": "JIRA_SYNC_ENABLED",
    "jira_sync_page_size": "JIRA_SYNC_PAGE_SIZE",
    "jira_sync_changelog_page_size": "JIRA_SYNC_CHANGELOG_PAGE_SIZE",
    "jira_sync_interval_seconds": "JIRA_SYNC_INTERVAL_SECONDS",
    "jira_field_story_points": "JIRA_FIELD_STORY_POINTS",
    "jira_field_severity": "JIRA_FIELD_SEVERITY",
    "jira_field_release": "JIRA_FIELD_RELEASE",
    "jira_field_sprint": "JIRA_FIELD_SPRINT",
    "jira_field_blocker": "JIRA_FIELD_BLOCKER",
    "jira_changelog_fix_version_fields": "JIRA_CHANGELOG_FIX_VERSION_FIELDS",
    "jira_changelog_sprint_fields": "JIRA_CHANGELOG_SPRINT_FIELDS",
    "jira_done_statuses": "JIRA_DONE_STATUSES",
    "jira_in_progress_statuses": "JIRA_IN_PROGRESS_STATUSES",
    "jira_high_severity_values": "JIRA_HIGH_SEVERITY_VALUES",
    "jira_bug_issue_types": "JIRA_BUG_ISSUE_TYPES",
    "jira_blocker_issue_types": "JIRA_BLOCKER_ISSUE_TYPES",
    "jira_blocker_severity_values": "JIRA_BLOCKER_SEVERITY_VALUES",
    "jira_blocked_statuses": "JIRA_BLOCKED_STATUSES",
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
    _validate_update_allowed(settings=current_settings, values=update_values)
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
        if field_name == "jira_sync_interval_seconds" and int(value) < 0:
            raise ValueError("Jira sync interval must be zero or greater")
        normalized[field_name] = value.strip() if isinstance(value, str) else value
    return normalized


def _build_candidate_settings(settings: Settings, values: dict[str, Any]) -> Settings:
    candidate_data = settings.model_dump()
    if "jira_api_token" in values:
        candidate_data["jira_api_token_file"] = ""
    candidate_data.update(values)
    return Settings(_env_file=None, **candidate_data)


def _validate_update_allowed(*, settings: Settings, values: dict[str, Any]) -> None:
    if "jira_api_token" in values and settings.deployment_mode != "desktop":
        raise ValueError(
            "Jira API token persistence is unavailable in this deployment mode; configure "
            "JIRA_API_TOKEN or JIRA_API_TOKEN_FILE externally and restart the backend"
        )
    if settings.deployment_mode == "docker" and not os.environ.get(CONFIG_FILE_ENV_VAR, "").strip():
        raise ValueError(
            "Docker configuration writes require a writable file mounted through "
            "LIGHTHOUSE_CONFIG_FILE"
        )


def _write_configuration(*, config_path: Path, values: dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    original = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    replacements = {
        JIRA_FIELD_TO_ENV[field_name]: _to_env_value(value)
        for field_name, value in values.items()
        if field_name != "jira_api_token"
    }
    updated = _update_env_text(original, replacements)
    _replace_file_atomically(config_path, updated)


def _update_env_text(original: str, replacements: dict[str, str]) -> str:
    if not replacements:
        return original

    remaining = dict(replacements)
    updated_keys: set[str] = set()
    output: list[str] = []
    for line in original.splitlines(keepends=True):
        match = _ENV_ASSIGNMENT.match(line)
        if match is None:
            output.append(line)
            continue
        key = match.group("key")
        if key in updated_keys:
            continue
        if key not in remaining:
            output.append(line)
            continue
        newline = "\r\n" if line.endswith("\r\n") else "\n"
        output.append(f"{match.group('prefix')}{key}={_quote_env_value(remaining.pop(key))}{newline}")
        updated_keys.add(key)

    if output and not output[-1].endswith(("\n", "\r")):
        output[-1] += "\n"
    output.extend(f"{key}={_quote_env_value(value)}\n" for key, value in remaining.items())
    return "".join(output)


def _quote_env_value(value: str) -> str:
    if value.replace("_", "").isalnum():
        return value
    return f"'{value.replace(chr(39), chr(92) + chr(39))}'"


def _replace_file_atomically(config_path: Path, contents: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=config_path.parent,
        prefix=f".{config_path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        if config_path.exists():
            os.chmod(temporary_path, config_path.stat().st_mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as temporary_file:
            descriptor = -1
            temporary_file.write(contents)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, config_path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def _apply_runtime_environment(*, values: dict[str, Any]) -> None:
    for field_name, value in values.items():
        if field_name == "jira_api_token" and get_settings().deployment_mode != "desktop":
            continue
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
        jira_api_token_configured=bool(settings.effective_jira_api_token.strip()),
        jira_project_key=settings.jira_project_key,
        jira_sync_enabled=settings.jira_sync_enabled,
        jira_sync_page_size=settings.jira_sync_page_size,
        jira_sync_changelog_page_size=settings.jira_sync_changelog_page_size,
        jira_sync_interval_seconds=settings.jira_sync_interval_seconds,
        jira_field_story_points=settings.jira_field_story_points,
        jira_field_severity=settings.jira_field_severity,
        jira_field_release=settings.jira_field_release,
        jira_field_sprint=settings.jira_field_sprint,
        jira_field_blocker=settings.jira_field_blocker,
        jira_changelog_fix_version_fields=settings.jira_changelog_fix_version_fields,
        jira_changelog_sprint_fields=settings.jira_changelog_sprint_fields,
        jira_done_statuses=settings.jira_done_statuses,
        jira_in_progress_statuses=settings.jira_in_progress_statuses,
        jira_high_severity_values=settings.jira_high_severity_values,
        jira_bug_issue_types=settings.jira_bug_issue_types,
        jira_blocker_issue_types=settings.jira_blocker_issue_types,
        jira_blocker_severity_values=settings.jira_blocker_severity_values,
        jira_blocked_statuses=settings.jira_blocked_statuses,
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
            settings.effective_jira_api_token.strip(),
            settings.jira_project_key.strip(),
            settings.jira_field_severity.strip(),
            settings.jira_field_release.strip(),
            settings.changelog_fix_version_fields,
            settings.done_statuses,
            settings.in_progress_statuses,
            settings.high_severity_values,
            settings.bug_issue_types,
        ]
    )


def _validate_jira_connection_settings(settings: Settings) -> None:
    forced_sync_settings = _build_candidate_settings(settings, {"jira_sync_enabled": True})
    forced_sync_settings.validate_startup_settings()
