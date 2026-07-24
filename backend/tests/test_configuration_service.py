import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

from app.config import get_settings
from app.schemas.configuration import JiraConfigurationUpdate
from app.services import configuration_service
from app.services.configuration_service import (
    CONFIG_FILE_ENV_VAR,
    get_jira_configuration,
    update_jira_configuration,
)


JIRA_ENV_DEFAULTS = {
    "JIRA_BASE_URL": "",
    "JIRA_USER_EMAIL": "",
    "JIRA_API_TOKEN": "",
    "JIRA_API_TOKEN_FILE": "",
    "JIRA_PROJECT_KEY": "",
    "JIRA_SYNC_ENABLED": "false",
    "JIRA_SYNC_PAGE_SIZE": "50",
    "JIRA_SYNC_CHANGELOG_PAGE_SIZE": "100",
    "JIRA_SYNC_INTERVAL_SECONDS": "0",
    "JIRA_FIELD_STORY_POINTS": "",
    "JIRA_FIELD_SEVERITY": "priority",
    "JIRA_FIELD_RELEASE": "fixVersions",
    "JIRA_FIELD_SPRINT": "",
    "JIRA_FIELD_BLOCKER": "",
    "JIRA_CHANGELOG_FIX_VERSION_FIELDS": "fix version,fixversion",
    "JIRA_CHANGELOG_SPRINT_FIELDS": "sprint",
    "JIRA_DONE_STATUSES": "done,closed,resolved",
    "JIRA_IN_PROGRESS_STATUSES": "in progress,in development,in review,in testing",
    "JIRA_HIGH_SEVERITY_VALUES": "high,highest,critical",
    "JIRA_BUG_ISSUE_TYPES": "bug",
    "JIRA_BLOCKER_ISSUE_TYPES": "blocker,incident",
    "JIRA_BLOCKER_SEVERITY_VALUES": "blocker,highest,critical",
    "JIRA_BLOCKED_STATUSES": "blocked",
}


def _isolate_jira_environment(monkeypatch: pytest.MonkeyPatch, config_path: Path) -> None:
    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config_path))
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("DEPLOYMENT_MODE", "local-browser")
    monkeypatch.setenv("APP_HOST", "127.0.0.1")
    monkeypatch.setenv("CORS_ORIGINS", "http://127.0.0.1:5173")
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN", "")
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN_FILE", "")
    for env_name, value in JIRA_ENV_DEFAULTS.items():
        monkeypatch.setenv(env_name, value)
    get_settings.cache_clear()


def test_get_jira_configuration_masks_token_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "backend.env"
    _isolate_jira_environment(monkeypatch, config_path)
    monkeypatch.setenv("JIRA_API_TOKEN", "secret-token")
    get_settings.cache_clear()

    try:
        response = get_jira_configuration()
    finally:
        get_settings.cache_clear()

    assert response.config_path == str(config_path.resolve())
    assert response.jira_api_token_configured is True
    assert "secret-token" not in response.model_dump_json()


def test_update_jira_configuration_writes_env_and_refreshes_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "backend.env"
    config_path.write_text("DATABASE_URL=sqlite+pysqlite:///./data/lighthouse.db\n", encoding="utf-8")
    _isolate_jira_environment(monkeypatch, config_path)
    monkeypatch.setenv("DEPLOYMENT_MODE", "desktop")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///desktop.db")
    monkeypatch.setenv("CORS_ORIGINS", "")
    monkeypatch.setenv("LIGHTHOUSE_API_TOKEN", "desktop-api-token")
    get_settings.cache_clear()

    try:
        response = update_jira_configuration(
            JiraConfigurationUpdate(
                jira_base_url=" https://example.atlassian.net ",
                jira_user_email="user@example.com",
                jira_api_token="new-token",
                jira_project_key="LHPM",
                jira_sync_enabled=True,
                jira_sync_interval_seconds=1800,
                jira_field_story_points="customfield_10016",
                jira_field_sprint="customfield_10020",
                jira_done_statuses="Done,Released",
                jira_bug_issue_types="Bug,Defect",
            )
        )
        refreshed_settings = get_settings()
    finally:
        get_settings.cache_clear()

    config_text = config_path.read_text(encoding="utf-8")
    config_values = dotenv_values(config_path)
    assert "DATABASE_URL=sqlite+pysqlite:///./data/lighthouse.db" in config_text
    assert config_values["JIRA_BASE_URL"] == "https://example.atlassian.net"
    assert "JIRA_API_TOKEN" not in config_values
    assert os.environ["JIRA_API_TOKEN"] == "new-token"
    assert os.environ["JIRA_SYNC_ENABLED"] == "true"
    assert config_values["JIRA_SYNC_INTERVAL_SECONDS"] == "1800"
    assert response.jira_base_url == "https://example.atlassian.net"
    assert response.jira_api_token_configured is True
    assert response.is_complete is True
    assert response.jira_sync_interval_seconds == 1800
    assert refreshed_settings.jira_project_key == "LHPM"
    assert refreshed_settings.jira_field_story_points == "customfield_10016"
    assert refreshed_settings.done_statuses == frozenset({"done", "released"})
    assert refreshed_settings.bug_issue_types == frozenset({"bug", "defect"})
    assert config_values["JIRA_DONE_STATUSES"] == "Done,Released"
    assert config_values["JIRA_BUG_ISSUE_TYPES"] == "Bug,Defect"


@pytest.mark.parametrize("deployment_mode", ["local-browser", "docker"])
def test_non_electron_update_rejects_jira_token_without_mutating_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    deployment_mode: str,
) -> None:
    config_path = tmp_path / "backend.env"
    original = "# preserved\nJIRA_PROJECT_KEY=OLD\n"
    config_path.write_text(original, encoding="utf-8")
    _isolate_jira_environment(monkeypatch, config_path)
    monkeypatch.setenv("DEPLOYMENT_MODE", deployment_mode)
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="JIRA_API_TOKEN or JIRA_API_TOKEN_FILE"):
        update_jira_configuration(
            JiraConfigurationUpdate(jira_api_token="must-not-persist", jira_project_key="NEW")
        )

    assert config_path.read_text(encoding="utf-8") == original
    assert os.environ["JIRA_API_TOKEN"] == ""
    assert get_settings().jira_project_key == ""


def test_nonsecret_configuration_write_is_atomic_and_preserves_comments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "backend.env"
    config_path.write_text(
        "# operator note\nDATABASE_URL=sqlite+pysqlite:///existing.db\nJIRA_PROJECT_KEY=OLD\n",
        encoding="utf-8",
    )
    _isolate_jira_environment(monkeypatch, config_path)

    try:
        response = update_jira_configuration(
            JiraConfigurationUpdate(jira_project_key="NEW", jira_sync_enabled=False)
        )
    finally:
        get_settings.cache_clear()

    updated = config_path.read_text(encoding="utf-8")
    assert "# operator note" in updated
    assert "DATABASE_URL=sqlite+pysqlite:///existing.db" in updated
    assert "JIRA_PROJECT_KEY=NEW" in updated
    assert response.jira_project_key == "NEW"


def test_atomic_replace_failure_leaves_existing_configuration_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "backend.env"
    original = "# preserved\nJIRA_PROJECT_KEY=OLD\n"
    config_path.write_text(original, encoding="utf-8")
    _isolate_jira_environment(monkeypatch, config_path)

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("synthetic atomic replace failure")

    monkeypatch.setattr(configuration_service.os, "replace", fail_replace)

    with pytest.raises(OSError, match="synthetic atomic replace failure"):
        update_jira_configuration(JiraConfigurationUpdate(jira_project_key="NEW"))

    assert config_path.read_text(encoding="utf-8") == original
    assert not tuple(tmp_path.glob(".backend.env.*.tmp"))


def test_docker_configuration_write_requires_explicit_mounted_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "backend.env"
    _isolate_jira_environment(monkeypatch, config_path)
    monkeypatch.setenv("DEPLOYMENT_MODE", "docker")
    monkeypatch.delenv(CONFIG_FILE_ENV_VAR)
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="LIGHTHOUSE_CONFIG_FILE"):
        update_jira_configuration(JiraConfigurationUpdate(jira_project_key="NEW"))

    assert not config_path.exists()


def test_update_jira_configuration_rejects_overlapping_status_classifications(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "backend.env"
    config_path.write_text("JIRA_SYNC_ENABLED=false\n", encoding="utf-8")
    _isolate_jira_environment(monkeypatch, config_path)

    try:
        with pytest.raises(ValueError, match="must not overlap"):
            update_jira_configuration(
                JiraConfigurationUpdate(
                    jira_done_statuses="Done,Shared",
                    jira_in_progress_statuses="Shared,Building",
                )
            )
    finally:
        get_settings.cache_clear()

    assert config_path.read_text(encoding="utf-8") == "JIRA_SYNC_ENABLED=false\n"


def test_update_jira_configuration_validates_sync_settings_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "backend.env"
    config_path.write_text("JIRA_SYNC_ENABLED=false\n", encoding="utf-8")
    _isolate_jira_environment(monkeypatch, config_path)

    try:
        with pytest.raises(ValueError, match="Missing required Jira startup settings"):
            update_jira_configuration(JiraConfigurationUpdate(jira_sync_enabled=True))
    finally:
        get_settings.cache_clear()

    assert config_path.read_text(encoding="utf-8") == "JIRA_SYNC_ENABLED=false\n"


@pytest.mark.asyncio
async def test_jira_connection_test_validates_required_values_without_sync_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "backend.env"
    _isolate_jira_environment(monkeypatch, config_path)

    try:
        response = await configuration_service.test_jira_connection(JiraConfigurationUpdate(jira_base_url=""))
    finally:
        get_settings.cache_clear()

    assert response.ok is False
    assert "Missing required Jira startup settings" in response.message


@pytest.mark.asyncio
async def test_jira_connection_test_calls_jira_and_reports_project_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "backend.env"
    _isolate_jira_environment(monkeypatch, config_path)

    class FakeJiraService:
        def __init__(self, *, settings):
            self.settings = settings

        async def validate_auth(self) -> dict[str, str]:
            return {"accountId": "account-1", "displayName": "Ada Lovelace"}

        async def get_project_versions(self, *, project_key: str):
            assert project_key == "LHPM"
            return [{"id": "10001"}, {"id": "10002"}]

        async def aclose(self) -> None:
            closed_services.append(self)

    closed_services: list[FakeJiraService] = []

    monkeypatch.setattr(configuration_service, "JiraService", FakeJiraService)

    try:
        response = await configuration_service.test_jira_connection(
            JiraConfigurationUpdate(
                jira_base_url="https://example.atlassian.net",
                jira_user_email="user@example.com",
                jira_api_token="token",
                jira_project_key="LHPM",
                jira_field_severity="priority",
                jira_field_release="fixVersions",
                jira_changelog_fix_version_fields="fix version,fixversion",
            )
        )
    finally:
        get_settings.cache_clear()

    assert response.ok is True
    assert response.account_id == "account-1"
    assert response.display_name == "Ada Lovelace"
    assert response.project_key == "LHPM"
    assert response.project_accessible is True
    assert "found 2 releases" in response.message
    assert len(closed_services) == 1


@pytest.mark.asyncio
async def test_jira_connection_candidate_token_is_transient_and_overrides_file_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "backend.env"
    token_file = tmp_path / "jira-token"
    token_file.write_text("external-token", encoding="utf-8")
    _isolate_jira_environment(monkeypatch, config_path)
    monkeypatch.setenv("JIRA_API_TOKEN_FILE", str(token_file))
    get_settings.cache_clear()
    captured_tokens: list[str] = []

    class FakeJiraService:
        def __init__(self, *, settings):
            captured_tokens.append(settings.effective_jira_api_token)

        async def validate_auth(self) -> dict[str, str]:
            return {"accountId": "account-1"}

        async def get_project_versions(self, *, project_key: str):
            return []

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(configuration_service, "JiraService", FakeJiraService)

    response = await configuration_service.test_jira_connection(
        JiraConfigurationUpdate(
            jira_base_url="https://example.atlassian.net",
            jira_user_email="user@example.com",
            jira_api_token="transient-token",
            jira_project_key="LHPM",
        )
    )

    assert response.ok is True
    assert captured_tokens == ["transient-token"]
    assert os.environ["JIRA_API_TOKEN"] == ""
    assert os.environ["JIRA_API_TOKEN_FILE"] == str(token_file)
    assert not config_path.exists()
    assert get_settings().effective_jira_api_token == "external-token"


@pytest.mark.asyncio
async def test_failed_connection_candidate_leaves_configuration_and_runtime_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "backend.env"
    original = "# preserved\nJIRA_PROJECT_KEY=ORIGINAL\n"
    config_path.write_text(original, encoding="utf-8")
    _isolate_jira_environment(monkeypatch, config_path)

    class FailingJiraService:
        def __init__(self, *, settings):
            assert settings.effective_jira_api_token == "failed-candidate-token"

        async def validate_auth(self) -> dict[str, str]:
            raise configuration_service.JiraServiceError("Jira authentication failed")

        async def get_project_versions(self, *, project_key: str):
            raise AssertionError("project access must not run after failed authentication")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(configuration_service, "JiraService", FailingJiraService)

    response = await configuration_service.test_jira_connection(
        JiraConfigurationUpdate(
            jira_base_url="https://example.atlassian.net",
            jira_user_email="operator@example.com",
            jira_api_token="failed-candidate-token",
            jira_project_key="CANDIDATE",
        )
    )

    assert response.ok is False
    assert config_path.read_text(encoding="utf-8") == original
    assert os.environ["JIRA_API_TOKEN"] == ""
    assert os.environ["JIRA_PROJECT_KEY"] == ""
    assert "failed-candidate-token" not in response.model_dump_json()
