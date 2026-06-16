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


def _seed_release(
    session: Session,
    release_id: str = "REL-1",
    name: str = "Release 1",
    project_key: str = "LHPM",
) -> Release:
    now = datetime.now(UTC)
    release = Release(
        release_id=release_id,
        name=name,
        project_key=project_key,
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


def _seed_issue(session: Session, release_id: str, issue_key: str) -> Issue:
    now = datetime.now(UTC)
    issue = Issue(
        issue_key=issue_key,
        summary="Example issue",
        issue_type="Bug",
        status="Open",
        priority="High",
        assignee="dev1",
        release_id=release_id,
        is_blocker=False,
        created_at=now,
        updated_at=now,
    )
    session.add(issue)
    session.commit()
    return issue


def test_get_releases_returns_paginated_list(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, "REL-1")
        _seed_release(session, "REL-2")

    response = client.get("/releases?skip=0&limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["skip"] == 0
    assert payload["limit"] == 1
    assert payload["total"] == 2
    assert len(payload["items"]) == 1


def test_get_releases_filters_by_project_key(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, "LHPM-REL-1", name="Release 1", project_key="LHPM")
        _seed_release(session, "OTHER-REL-1", name="Release 1", project_key="OTHER")

    response = client.get("/releases?project_key=LHPM")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["release_id"] == "LHPM-REL-1"
    assert payload["items"][0]["name"] == "Release 1"
    assert payload["items"][0]["project_key"] == "LHPM"


def test_get_releases_project_filter_is_case_insensitive(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, "LHPM-REL-1", project_key="LHPM")
        _seed_release(session, "OTHER-REL-1", project_key="OTHER")

    response = client.get("/releases?project_key=lhpm")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["release_id"] == "LHPM-REL-1"


def test_get_release_by_id_returns_release(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, "REL-42")

    response = client.get("/releases/REL-42")

    assert response.status_code == 200
    assert response.json()["release_id"] == "REL-42"


def test_get_release_by_id_not_found(client: TestClient) -> None:
    response = client.get("/releases/DOES-NOT-EXIST")

    assert response.status_code == 404
    assert response.json()["detail"] == "Release 'DOES-NOT-EXIST' not found"


def test_get_release_issues_returns_paginated_issues(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, "REL-10")
        _seed_issue(session, "REL-10", "LHPM-1")
        _seed_issue(session, "REL-10", "LHPM-2")

    response = client.get("/releases/REL-10/issues?skip=0&limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 1


def test_get_release_issues_release_not_found(client: TestClient) -> None:
    response = client.get("/releases/UNKNOWN/issues")

    assert response.status_code == 404
    assert response.json()["detail"] == "Release 'UNKNOWN' not found"
