from collections.abc import Generator
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import Issue, IssueHistory, MetricSnapshot, Release


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


def _seed_release(session: Session, release_id: str = "REL-1", name: str = "Release 1") -> None:
    now = datetime.now(UTC)
    session.add(
        Release(
            release_id=release_id,
            name=name,
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


def _seed_issue(session: Session, issue_key: str, release_id: str, status: str, is_blocker: bool = False) -> None:
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


def _seed_history(
    session: Session,
    issue_key: str,
    field_name: str,
    old_value: str | None,
    new_value: str | None,
    changed_at: datetime,
) -> None:
    session.add(
        IssueHistory(
            issue_key=issue_key,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            changed_at=changed_at,
        )
    )


def _seed_snapshot(
    session: Session,
    release_id: str,
    snapshot_at: datetime,
    open_blockers: int,
) -> None:
    session.add(
        MetricSnapshot(
            release_id=release_id,
            snapshot_at=snapshot_at,
            open_blockers=open_blockers,
            open_high_severity_bugs=open_blockers,
            scope_completed_pct=float(open_blockers),
            scope_churn_7d_pct=float(open_blockers),
            median_cycle_time_days=float(open_blockers),
            reopen_rate_pct=float(open_blockers),
        )
    )


def test_get_release_metrics_not_found_when_release_missing(client: TestClient) -> None:
    response = client.get("/releases/UNKNOWN/metrics")

    assert response.status_code == 404
    assert response.json()["detail"] == "Release 'UNKNOWN' not found"


def test_get_release_metrics_returns_empty_state_when_snapshot_missing(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")

    response = client.get("/releases/REL-1/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["release_id"] == "REL-1"
    assert payload["snapshot_at"] is None
    assert payload["metric_names"] == [
        "open_blockers",
        "open_high_severity_bugs",
        "scope_completed_pct",
        "scope_churn_7d_pct",
        "median_cycle_time_days",
        "reopen_rate_pct",
    ]
    assert payload["metric_thresholds"] is None
    assert payload["is_computed"] is False
    assert payload["snapshot_age_hours"] is None
    assert payload["metrics"] == {
        "open_blockers": None,
        "open_high_severity_bugs": None,
        "scope_completed_pct": None,
        "scope_churn_7d_pct": None,
        "median_cycle_time_days": None,
        "reopen_rate_pct": None,
    }


def test_get_release_charts_returns_empty_series_when_snapshot_missing(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")

    response = client.get("/releases/REL-1/charts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["release_id"] == "REL-1"
    assert payload["metric_names"] == [
        "open_blockers",
        "open_high_severity_bugs",
        "scope_completed_pct",
        "scope_churn_7d_pct",
        "median_cycle_time_days",
        "reopen_rate_pct",
    ]
    assert payload["point_count"] == 0
    assert payload["series"] == {
        "open_blockers": [],
        "open_high_severity_bugs": [],
        "scope_completed_pct": [],
        "scope_churn_7d_pct": [],
        "median_cycle_time_days": [],
        "reopen_rate_pct": [],
    }


def test_recompute_release_metrics_creates_snapshot(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1", name="Release 1")
        _seed_issue(session, "LHPM-1", "REL-1", "In Progress", is_blocker=True)
        _seed_issue(session, "LHPM-2", "REL-1", "Done", is_blocker=False)
        now = datetime.now(UTC)
        _seed_history(session, "LHPM-2", "status", "To Do", "In Progress", now - timedelta(days=3))
        _seed_history(session, "LHPM-2", "status", "In Progress", "Done", now - timedelta(days=1))
        _seed_history(session, "LHPM-2", "fix version", "Release 0", "Release 1", now - timedelta(days=2))
        session.commit()

    recompute = client.post("/releases/REL-1/recompute")
    assert recompute.status_code == 200
    payload = recompute.json()
    assert payload["release_id"] == "REL-1"
    assert payload["status"] == "ok"

    response = client.get("/releases/REL-1/metrics")
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["release_id"] == "REL-1"
    assert metrics["snapshot_at"] is not None
    assert metrics["is_computed"] is True
    assert isinstance(metrics["snapshot_age_hours"], float)
    assert metrics["snapshot_age_hours"] >= 0.0
    assert metrics["metric_names"] == [
        "open_blockers",
        "open_high_severity_bugs",
        "scope_completed_pct",
        "scope_churn_7d_pct",
        "median_cycle_time_days",
        "reopen_rate_pct",
    ]
    assert metrics["metric_thresholds"] == {
        "open_blockers_red": 0,
        "open_high_severity_bugs_red": 1,
        "open_high_severity_bugs_yellow": 0,
        "scope_churn_7d_pct_red": 20.0,
        "scope_churn_7d_pct_yellow": 10.0,
        "reopen_rate_pct_red": 15.0,
        "reopen_rate_pct_yellow": 10.0,
        "median_cycle_time_days_yellow": 7.0,
    }
    assert metrics["metrics"]["open_blockers"] == 1
    assert metrics["metrics"]["open_high_severity_bugs"] == 1
    assert metrics["metrics"]["scope_completed_pct"] == 50.0
    assert metrics["metrics"]["scope_churn_7d_pct"] == 50.0
    assert metrics["metrics"]["reopen_rate_pct"] == 0.0

    charts = client.get("/releases/REL-1/charts")
    assert charts.status_code == 200
    charts_payload = charts.json()
    assert charts_payload["metric_names"] == [
        "open_blockers",
        "open_high_severity_bugs",
        "scope_completed_pct",
        "scope_churn_7d_pct",
        "median_cycle_time_days",
        "reopen_rate_pct",
    ]
    assert charts_payload["point_count"] == 1
    series = charts_payload["series"]
    assert len(series["open_blockers"]) == 1
    assert series["open_blockers"][0]["value"] == 1
    assert len(series["scope_completed_pct"]) == 1
    assert series["scope_completed_pct"][0]["value"] == 50.0


def test_recompute_release_metrics_returns_404_when_missing_release(client: TestClient) -> None:
    response = client.post("/releases/MISSING/recompute")

    assert response.status_code == 404
    assert "Release not found" in response.json()["detail"]


def test_get_release_charts_not_found_when_release_missing(client: TestClient) -> None:
    response = client.get("/releases/UNKNOWN/charts")

    assert response.status_code == 404
    assert response.json()["detail"] == "Release 'UNKNOWN' not found"


def test_get_release_charts_limit_param(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        base = datetime(2026, 4, 1, tzinfo=UTC)
        _seed_snapshot(session, "REL-1", base + timedelta(days=1), open_blockers=1)
        _seed_snapshot(session, "REL-1", base + timedelta(days=2), open_blockers=2)
        _seed_snapshot(session, "REL-1", base + timedelta(days=3), open_blockers=3)
        session.commit()

    response = client.get("/releases/REL-1/charts?limit=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["point_count"] == 2
    points = payload["series"]["open_blockers"]
    assert len(points) == 2
    assert [point["value"] for point in points] == [2, 3]


def test_get_release_charts_from_to_params(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        base = datetime(2026, 4, 1, tzinfo=UTC)
        _seed_snapshot(session, "REL-1", base + timedelta(days=1), open_blockers=1)
        _seed_snapshot(session, "REL-1", base + timedelta(days=2), open_blockers=2)
        _seed_snapshot(session, "REL-1", base + timedelta(days=3), open_blockers=3)
        session.commit()

    from_param = (datetime(2026, 4, 2, tzinfo=UTC)).isoformat().replace("+00:00", "Z")
    to_param = (datetime(2026, 4, 3, tzinfo=UTC)).isoformat().replace("+00:00", "Z")
    response = client.get(f"/releases/REL-1/charts?from={from_param}&to={to_param}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["point_count"] == 2
    points = payload["series"]["open_blockers"]
    assert len(points) == 2
    assert [point["value"] for point in points] == [1, 2]


def test_get_release_charts_invalid_from_to_range(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")

    from_param = (datetime(2026, 4, 3, tzinfo=UTC)).isoformat().replace("+00:00", "Z")
    to_param = (datetime(2026, 4, 2, tzinfo=UTC)).isoformat().replace("+00:00", "Z")
    response = client.get(f"/releases/REL-1/charts?from={from_param}&to={to_param}")

    assert response.status_code == 400
    assert response.json()["detail"] == "'from' must be less than or equal to 'to'"
