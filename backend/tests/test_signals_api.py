from collections.abc import Generator
from datetime import UTC, datetime

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import Issue, MetricSnapshot, Release


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

    def override_get_db_session() -> Generator[Session, None, None]:
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


def _seed_release(session: Session, release_id: str = "REL-1") -> None:
    now = datetime.now(UTC)
    session.add(
        Release(
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
    )
    session.commit()


def _seed_snapshot(
    session: Session,
    release_id: str,
    open_blockers: int,
    open_high_severity_bugs: int,
    scope_churn_7d_pct: float,
    reopen_rate_pct: float,
    median_cycle_time_days: float | None,
) -> None:
    session.add(
        MetricSnapshot(
            release_id=release_id,
            snapshot_at=datetime.now(UTC),
            open_blockers=open_blockers,
            open_high_severity_bugs=open_high_severity_bugs,
            scope_completed_pct=50.0,
            scope_churn_7d_pct=scope_churn_7d_pct,
            median_cycle_time_days=median_cycle_time_days,
            reopen_rate_pct=reopen_rate_pct,
        )
    )
    session.commit()


def _seed_issue(session: Session, issue_key: str, release_id: str, status: str, is_blocker: bool) -> None:
    now = datetime.now(UTC)
    session.add(
        Issue(
            issue_key=issue_key,
            summary="Issue",
            issue_type="Bug",
            status=status,
            priority="High",
            assignee="alice",
            release_id=release_id,
            is_blocker=is_blocker,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def test_get_release_signal_not_found_when_release_missing(client: TestClient) -> None:
    response = client.get("/releases/UNKNOWN/signal")

    assert response.status_code == 404
    assert response.json()["detail"] == "Release 'UNKNOWN' not found"


def test_get_release_signal_empty_state_when_not_computed(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")

    response = client.get("/releases/REL-1/signal")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "release_id": "REL-1",
        "signal": None,
        "reasons": [],
        "updated_at": None,
    }


def test_get_release_signal_after_metrics_recompute_returns_red(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(session, issue_key="LHPM-1", release_id="REL-1", status="In Progress", is_blocker=True)

    recompute = client.post("/releases/REL-1/recompute")
    assert recompute.status_code == 200

    response = client.get("/releases/REL-1/signal")
    assert response.status_code == 200
    payload = response.json()
    assert payload["release_id"] == "REL-1"
    assert payload["signal"] == "RED"
    assert any("blocker" in reason.lower() for reason in payload["reasons"])


def test_get_release_signal_after_metrics_recompute_returns_green(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_snapshot(
            session,
            release_id="REL-1",
            open_blockers=0,
            open_high_severity_bugs=0,
            scope_churn_7d_pct=5.0,
            reopen_rate_pct=1.0,
            median_cycle_time_days=2.0,
        )

    recompute = client.post("/releases/REL-1/recompute")
    assert recompute.status_code == 200

    response = client.get("/releases/REL-1/signal")
    assert response.status_code == 200
    payload = response.json()
    assert payload["signal"] == "GREEN"
    assert payload["reasons"] == ["No major risk indicators"]
