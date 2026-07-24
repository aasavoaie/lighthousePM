from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.services import configuration_service
from tests.api_contract_snapshots import assert_api_contract_snapshot


JIRA_CONTRACT_SECRET = "contract-jira-secret"
NEUTRAL_CONFIG_PATH = "lighthouse-contract.env"


@pytest.fixture
def configuration_sync_contract_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        class_=Session,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db_session() -> Generator[Session, None, None]:
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    settings = {
        "LIGHTHOUSE_CONFIG_FILE": str(tmp_path / "absent.env"),
        "APP_ENV": "dev",
        "DEPLOYMENT_MODE": "local-browser",
        "APP_HOST": "127.0.0.1",
        "CORS_ORIGINS": "http://127.0.0.1:5173",
        "DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "POSTGRES_PASSWORD": "",
        "POSTGRES_PASSWORD_FILE": "",
        "LIGHTHOUSE_API_TOKEN": "",
        "LIGHTHOUSE_API_TOKEN_FILE": "",
        "JIRA_BASE_URL": "https://example.atlassian.net",
        "JIRA_USER_EMAIL": "contract@example.test",
        "JIRA_API_TOKEN": JIRA_CONTRACT_SECRET,
        "JIRA_API_TOKEN_FILE": "",
        "JIRA_PROJECT_KEY": "LHPM",
        "JIRA_SYNC_ENABLED": "true",
        "JIRA_SYNC_PAGE_SIZE": "25",
        "JIRA_SYNC_CHANGELOG_PAGE_SIZE": "75",
        "JIRA_SYNC_INTERVAL_SECONDS": "300",
        "JIRA_FIELD_STORY_POINTS": "customfield_10016",
        "JIRA_FIELD_SEVERITY": "priority",
        "JIRA_FIELD_RELEASE": "fixVersions",
        "JIRA_FIELD_SPRINT": "customfield_10020",
        "JIRA_FIELD_BLOCKER": "customfield_10021",
        "JIRA_BLOCKER_TRUE_VALUES": "true,yes,1,blocker",
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
    for name, value in settings.items():
        monkeypatch.setenv(name, value)

    monkeypatch.setattr(
        configuration_service,
        "get_configuration_file_path",
        lambda: Path(NEUTRAL_CONFIG_PATH),
    )
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(main_module, "start_scheduler", lambda settings: None)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: None)
    get_settings.cache_clear()

    configured_app: FastAPI = main_module.create_app()
    configured_app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        with TestClient(configured_app) as client:
            yield client
    finally:
        configured_app.dependency_overrides.clear()
        get_settings.cache_clear()
        engine.dispose()


def test_jira_configuration_response_matches_redacted_contract(
    configuration_sync_contract_client: TestClient,
    tmp_path: Path,
) -> None:
    response = configuration_sync_contract_client.get("/config/jira")

    assert response.status_code == 200
    assert response.json()["config_path"] == NEUTRAL_CONFIG_PATH
    assert response.json()["jira_api_token_configured"] is True
    assert response.json()["is_complete"] is True
    assert JIRA_CONTRACT_SECRET not in response.text
    assert str(tmp_path) not in response.text
    assert_api_contract_snapshot(
        "configuration.jira.redacted.200",
        status_code=response.status_code,
        payload=response.json(),
    )


def test_successful_jira_sync_response_matches_contract(
    configuration_sync_contract_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_sync(self, session: Session) -> dict[str, int | str]:
        return {
            "project_key": "LHPM",
            "releases_fetched": 3,
            "releases_inserted": 2,
            "releases_updated": 1,
            "sprints_inserted": 4,
            "sprints_updated": 2,
            "issues_fetched": 27,
            "issues_inserted": 20,
            "issues_updated": 5,
            "issues_skipped": 2,
            "issue_details_skipped_unchanged": 2,
            "history_fetched": 41,
            "history_inserted": 38,
            "history_skipped": 3,
            "changelogs_skipped_unchanged": 2,
        }

    monkeypatch.setattr(
        "app.services.sync_service.SyncService.sync_from_jira",
        fake_sync,
    )
    response = configuration_sync_contract_client.post("/sync/jira")

    assert response.status_code == 200
    assert response.json()["project_key"] == "LHPM"
    assert JIRA_CONTRACT_SECRET not in response.text
    assert_api_contract_snapshot(
        "sync.jira.success.200",
        status_code=response.status_code,
        payload=response.json(),
    )
