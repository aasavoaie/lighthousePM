import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

from app.config import get_settings
from app.schemas.configuration import JiraConfigurationUpdate
from app.services.configuration_service import (
    CONFIG_FILE_ENV_VAR,
    get_jira_configuration,
    update_jira_configuration,
)


JIRA_ENV_DEFAULTS = {
    "JIRA_BASE_URL": "",
    "JIRA_USER_EMAIL": "",
    "JIRA_API_TOKEN": "",
    "JIRA_PROJECT_KEY": "",
    "JIRA_SYNC_ENABLED": "false",
    "JIRA_SYNC_PAGE_SIZE": "50",
    "JIRA_SYNC_CHANGELOG_PAGE_SIZE": "100",
    "JIRA_FIELD_STORY_POINTS": "",
    "JIRA_FIELD_SEVERITY": "priority",
    "JIRA_FIELD_RELEASE": "fixVersions",
    "JIRA_FIELD_SPRINT": "",
    "JIRA_FIELD_BLOCKER": "",
    "JIRA_CHANGELOG_FIX_VERSION_FIELDS": "fix version,fixversion",
    "JIRA_CHANGELOG_SPRINT_FIELDS": "sprint",
}


def _isolate_jira_environment(monkeypatch: pytest.MonkeyPatch, config_path: Path) -> None:
    monkeypatch.setenv(CONFIG_FILE_ENV_VAR, str(config_path))
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

    try:
        response = update_jira_configuration(
            JiraConfigurationUpdate(
                jira_base_url=" https://example.atlassian.net ",
                jira_user_email="user@example.com",
                jira_api_token="new-token",
                jira_project_key="LHPM",
                jira_sync_enabled=True,
                jira_field_story_points="customfield_10016",
                jira_field_sprint="customfield_10020",
            )
        )
        refreshed_settings = get_settings()
    finally:
        get_settings.cache_clear()

    config_text = config_path.read_text(encoding="utf-8")
    config_values = dotenv_values(config_path)
    assert "DATABASE_URL=sqlite+pysqlite:///./data/lighthouse.db" in config_text
    assert config_values["JIRA_BASE_URL"] == "https://example.atlassian.net"
    assert config_values["JIRA_API_TOKEN"] == "new-token"
    assert os.environ["JIRA_SYNC_ENABLED"] == "true"
    assert response.jira_base_url == "https://example.atlassian.net"
    assert response.jira_api_token_configured is True
    assert refreshed_settings.jira_project_key == "LHPM"
    assert refreshed_settings.jira_field_story_points == "customfield_10016"


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
