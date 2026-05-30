from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.services.jira_errors import JiraAuthError
from app.services.sync_service import SyncServiceError


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)

    def override_get_db_session():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session

    original_init_db = main_module.init_db
    main_module.init_db = lambda: None
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        main_module.init_db = original_init_db
        app.dependency_overrides.clear()


def test_post_sync_jira_returns_sync_counts(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_sync(self, session: Session) -> dict[str, int | str]:
        return {
            "project_key": "LHPM",
            "releases_fetched": 1,
            "releases_inserted": 1,
            "releases_updated": 0,
            "sprints_inserted": 0,
            "sprints_updated": 0,
            "issues_fetched": 4,
            "issues_inserted": 3,
            "issues_updated": 1,
            "issues_skipped": 0,
            "history_fetched": 6,
            "history_inserted": 5,
            "history_skipped": 1,
        }

    monkeypatch.setattr("app.services.sync_service.SyncService.sync_from_jira", fake_sync)

    response = client.post("/sync/jira")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_key"] == "LHPM"
    assert payload["issues_inserted"] == 3
    assert payload["history_inserted"] == 5


def test_post_sync_jira_returns_400_for_sync_service_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_sync_error(self, session: Session) -> dict[str, int | str]:
        raise SyncServiceError("JIRA_PROJECT_KEY must be configured for sync")

    monkeypatch.setattr("app.services.sync_service.SyncService.sync_from_jira", fake_sync_error)

    response = client.post("/sync/jira")

    assert response.status_code == 400
    assert response.json()["detail"] == "JIRA_PROJECT_KEY must be configured for sync"


def test_post_sync_jira_returns_401_for_jira_auth_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_sync_auth_error(self, session: Session) -> dict[str, int | str]:
        raise SyncServiceError("Jira sync failed: auth failed") from JiraAuthError("auth failed")

    monkeypatch.setattr("app.services.sync_service.SyncService.sync_from_jira", fake_sync_auth_error)

    response = client.post("/sync/jira")

    assert response.status_code == 401
    assert response.json()["detail"] == "Jira sync failed: auth failed"
