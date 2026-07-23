from datetime import UTC, datetime
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
from app.models import Issue, Release


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    app.state.testing_session_local = TestingSessionLocal

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
        del app.state.testing_session_local
        main_module.init_db = original_init_db
        app.dependency_overrides.clear()


def _seed_release(session: Session, release_id: str = "REL-1") -> Release:
    now = datetime.now(UTC)
    release = Release(
        release_id=release_id,
        name="Release 1",
        project_key="LHPM",
        description="Seed release",
        status="active",
        start_date=now,
        release_date=None,
        created_at=now,
        updated_at=now,
    )
    session.add(release)
    session.commit()
    return release


def _seed_issue(
    session: Session,
    release_id: str,
    issue_key: str,
    *,
    issue_type: str | None = "Task",
    status: str | None = "Open",
) -> Issue:
    now = datetime.now(UTC)
    issue = Issue(
        issue_key=issue_key,
        summary="Example issue",
        issue_type=issue_type,
        status=status,
        priority="Medium",
        assignee="dev2",
        release_id=release_id,
        is_blocker=True,
        created_at=now,
        updated_at=now,
    )
    session.add(issue)
    session.commit()
    return issue


def test_get_issue_returns_issue(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, "REL-9")
        _seed_issue(session, "REL-9", "LHPM-99")

    response = client.get("/issues/LHPM-99")

    assert response.status_code == 200
    payload = response.json()
    assert payload["issue_key"] == "LHPM-99"
    assert payload["release_id"] == "REL-9"


def test_get_issue_not_found(client: TestClient) -> None:
    response = client.get("/issues/MISSING-1")

    assert response.status_code == 404
    assert response.json()["detail"] == "Issue 'MISSING-1' not found"


def test_get_issue_preserves_missing_classification_fields(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, "REL-9")
        _seed_issue(session, "REL-9", "LHPM-100", issue_type=None, status=None)

    response = client.get("/issues/LHPM-100")

    assert response.status_code == 200
    assert response.json()["issue_type"] is None
    assert response.json()["status"] is None
