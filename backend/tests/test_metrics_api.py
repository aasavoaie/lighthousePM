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
from app.models import Issue, IssueHistory, IssueSprint, MetricSnapshot, Release, Sprint
from app.services.analytics_service import AnalyticsService


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


def _seed_release(
    session: Session,
    release_id: str = "REL-1",
    name: str = "Release 1",
    project_key: str = "LHPM",
) -> None:
    now = datetime.now(UTC)
    session.add(
        Release(
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
    )
    session.commit()


def _seed_issue(
    session: Session,
    issue_key: str,
    release_id: str,
    status: str,
    is_blocker: bool = False,
    issue_type: str = "Bug",
    priority: str | None = "High",
    story_points: float | None = None,
) -> None:
    now = datetime.now(UTC)
    session.add(
        Issue(
            issue_key=issue_key,
            summary="Issue",
            issue_type=issue_type,
            status=status,
            priority=priority,
            assignee="alice",
            story_points=story_points,
            release_id=release_id,
            is_blocker=is_blocker,
            created_at=now,
            updated_at=now,
        )
    )


def _seed_sprint(
    session: Session,
    sprint_id: str,
    state: str,
    project_key: str = "LHPM",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    complete_date: datetime | None = None,
) -> None:
    now = datetime.now(UTC)
    session.add(
        Sprint(
            sprint_id=sprint_id,
            name=f"Sprint {sprint_id}",
            state=state,
            project_key=project_key,
            board_id="1",
            start_date=start_date,
            end_date=end_date,
            complete_date=complete_date if complete_date is not None else (now if state == "closed" else None),
            goal=None,
            created_at=now,
            updated_at=now,
        )
    )


def _link_issue_to_sprint(session: Session, issue_key: str, sprint_id: str) -> None:
    session.add(IssueSprint(issue_key=issue_key, sprint_id=sprint_id))


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
    assert payload["metric_issue_keys"] == {
        "open_blockers": [],
        "open_high_severity_bugs": [],
    }
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
    assert payload["sprint_velocity"] == {"points": [], "point_count": 0}


def test_get_release_charts_returns_four_closed_sprints_plus_active_velocity(client: TestClient) -> None:
    base = datetime(2026, 4, 1, tzinfo=UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        for index in range(1, 6):
            sprint_id = str(index)
            complete_date = base + timedelta(days=index)
            _seed_sprint(
                session,
                sprint_id=sprint_id,
                state="closed",
                start_date=complete_date - timedelta(days=14),
                end_date=complete_date,
                complete_date=complete_date,
            )
            issue_key = f"LHPM-C{index}"
            _seed_issue(session, issue_key, "REL-1", "Done", story_points=float(index))
            _link_issue_to_sprint(session, issue_key, sprint_id)

        _seed_sprint(
            session,
            sprint_id="99",
            state="active",
            start_date=base + timedelta(days=10),
            end_date=base + timedelta(days=24),
            complete_date=None,
        )
        _seed_issue(session, "LHPM-A1", "REL-1", "Done", story_points=8)
        _seed_issue(session, "LHPM-A2", "REL-1", "To Do", story_points=13)
        _link_issue_to_sprint(session, "LHPM-A1", "99")
        _link_issue_to_sprint(session, "LHPM-A2", "99")
        session.commit()

    response = client.get("/releases/REL-1/charts")

    assert response.status_code == 200
    velocity = response.json()["sprint_velocity"]
    assert velocity["point_count"] == 5
    assert [point["sprint_id"] for point in velocity["points"]] == ["2", "3", "4", "5", "99"]
    assert [point["velocity"] for point in velocity["points"]] == [2.0, 3.0, 4.0, 5.0, 8.0]
    active_point = velocity["points"][-1]
    assert active_point["completed_at"] is None
    assert active_point["state"] == "active"
    assert active_point["note"] == "Sprint In Progress"


def test_get_release_charts_returns_five_closed_sprints_without_active_velocity(client: TestClient) -> None:
    base = datetime(2026, 4, 1, tzinfo=UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        for index in range(1, 7):
            sprint_id = str(index)
            complete_date = base + timedelta(days=index)
            _seed_sprint(
                session,
                sprint_id=sprint_id,
                state="closed",
                start_date=complete_date - timedelta(days=14),
                end_date=complete_date,
                complete_date=complete_date,
            )
            issue_key = f"LHPM-C{index}"
            _seed_issue(session, issue_key, "REL-1", "Done", story_points=float(index))
            _link_issue_to_sprint(session, issue_key, sprint_id)
        session.commit()

    response = client.get("/releases/REL-1/charts")

    assert response.status_code == 200
    points = response.json()["sprint_velocity"]["points"]
    assert [point["sprint_id"] for point in points] == ["2", "3", "4", "5", "6"]
    assert all(point["note"] is None for point in points)


def test_get_release_charts_returns_available_sprint_velocity_when_fewer_than_five(client: TestClient) -> None:
    base = datetime(2026, 4, 1, tzinfo=UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        for index in range(1, 3):
            sprint_id = str(index)
            complete_date = base + timedelta(days=index)
            _seed_sprint(
                session,
                sprint_id=sprint_id,
                state="closed",
                start_date=complete_date - timedelta(days=14),
                end_date=complete_date,
                complete_date=complete_date,
            )
        session.commit()

    response = client.get("/releases/REL-1/charts")

    assert response.status_code == 200
    velocity = response.json()["sprint_velocity"]
    assert velocity["point_count"] == 2
    assert [point["sprint_id"] for point in velocity["points"]] == ["1", "2"]


def test_get_release_charts_filters_sprint_velocity_by_release_project_and_state(client: TestClient) -> None:
    base = datetime(2026, 4, 1, tzinfo=UTC)
    with app.state.testing_session_local() as session:
        now = datetime.now(UTC)
        _seed_release(session, release_id="REL-1", project_key="LHPM")
        _seed_sprint(session, "1", "closed", project_key="LHPM", complete_date=base + timedelta(days=1))
        _seed_sprint(session, "2", "future", project_key="LHPM", start_date=base + timedelta(days=2))
        _seed_sprint(session, "3", "closed", project_key="OTHER", complete_date=base + timedelta(days=3))
        session.add(
            Sprint(
                sprint_id="4",
                name="Sprint 4",
                state="closed",
                project_key="LHPM",
                board_id="1",
                start_date=None,
                end_date=None,
                complete_date=None,
                goal=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    response = client.get("/releases/REL-1/charts")

    assert response.status_code == 200
    points = response.json()["sprint_velocity"]["points"]
    assert [point["sprint_id"] for point in points] == ["1"]


def test_get_release_charts_sprint_velocity_uses_completed_effective_points(client: TestClient) -> None:
    base = datetime(2026, 4, 1, tzinfo=UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_sprint(session, "1", "closed", complete_date=base + timedelta(days=1))
        _seed_issue(session, "LHPM-1", "REL-1", "Done", story_points=5)
        _seed_issue(session, "LHPM-2", "REL-1", "Done", story_points=None)
        _seed_issue(session, "LHPM-3", "REL-1", "Done", story_points=-3)
        _seed_issue(session, "LHPM-4", "REL-1", "To Do", story_points=100)
        for issue_key in ["LHPM-1", "LHPM-2", "LHPM-3", "LHPM-4"]:
            _link_issue_to_sprint(session, issue_key, "1")
        session.commit()

    response = client.get("/releases/REL-1/charts")

    assert response.status_code == 200
    assert response.json()["sprint_velocity"]["points"][0]["velocity"] == 7.0


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
    assert metrics["metric_issue_keys"] == {
        "open_blockers": ["LHPM-1"],
        "open_high_severity_bugs": ["LHPM-1"],
    }

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

    admin_status = client.get("/admin/status")
    assert admin_status.status_code == 200
    admin_payload = admin_status.json()
    assert admin_payload["last_metrics_recompute_at"] is not None
    assert admin_payload["last_signal_recompute_at"] is not None


def test_recompute_release_metrics_returns_404_when_missing_release(client: TestClient) -> None:
    response = client.post("/releases/MISSING/recompute")

    assert response.status_code == 404
    assert "Release not found" in response.json()["detail"]


def test_release_metrics_returns_metric_issue_keys(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(session, "LHPM-1", "REL-1", "In Progress", is_blocker=True, issue_type="Story")
        _seed_issue(session, "LHPM-2", "REL-1", "To Do", issue_type="Bug", priority="Critical")
        _seed_issue(session, "LHPM-3", "REL-1", "Done", is_blocker=True, issue_type="Bug", priority="High")
        _seed_issue(session, "LHPM-4", "REL-1", "To Do", issue_type="Story", priority="High")
        session.commit()

    recompute = client.post("/releases/REL-1/recompute")
    response = client.get("/releases/REL-1/metrics")

    assert recompute.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["open_blockers"] == 1
    assert payload["metrics"]["open_high_severity_bugs"] == 1
    assert payload["metric_issue_keys"] == {
        "open_blockers": ["LHPM-1"],
        "open_high_severity_bugs": ["LHPM-2"],
    }


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


def test_recompute_all_release_metrics_recomputes_all_releases(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1", name="Release 1")
        _seed_release(session, release_id="REL-2", name="Release 2")

        _seed_issue(session, "LHPM-1", "REL-1", "In Progress", is_blocker=True)
        _seed_issue(session, "LHPM-2", "REL-1", "Done", is_blocker=False)
        _seed_issue(session, "LHPM-3", "REL-2", "In Progress", is_blocker=False)

        now = datetime.now(UTC)
        _seed_history(session, "LHPM-2", "status", "To Do", "In Progress", now - timedelta(days=3))
        _seed_history(session, "LHPM-2", "status", "In Progress", "Done", now - timedelta(days=1))
        _seed_history(session, "LHPM-2", "fix version", "Release 0", "Release 1", now - timedelta(days=2))
        session.commit()

    response = client.post("/releases/recompute-all")

    assert response.status_code == 200
    payload = response.json()
    assert payload["releases_total"] == 2
    assert payload["releases_recomputed"] == 2
    assert payload["releases_failed"] == 0
    assert isinstance(payload["elapsed_seconds"], float)
    assert payload["elapsed_seconds"] >= 0.0
    assert payload["errors"] == []

    rel_1_metrics = client.get("/releases/REL-1/metrics").json()
    rel_2_metrics = client.get("/releases/REL-2/metrics").json()
    assert rel_1_metrics["is_computed"] is True
    assert rel_1_metrics["snapshot_at"] is not None
    assert rel_2_metrics["is_computed"] is True
    assert rel_2_metrics["snapshot_at"] is not None


def test_recompute_all_release_metrics_is_best_effort(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1", name="Release 1")
        _seed_release(session, release_id="REL-2", name="Release 2")
        _seed_issue(session, "LHPM-1", "REL-1", "In Progress", is_blocker=False)
        _seed_issue(session, "LHPM-2", "REL-2", "In Progress", is_blocker=False)
        session.commit()

    original_recompute = AnalyticsService.recompute_release_metrics

    def recompute_with_injected_failure(
        self: AnalyticsService, session: Session, release_id: str
    ) -> MetricSnapshot:
        if release_id == "REL-2":
            raise ValueError("Synthetic recompute failure")
        return original_recompute(self, session, release_id)

    monkeypatch.setattr(AnalyticsService, "recompute_release_metrics", recompute_with_injected_failure)

    response = client.post("/releases/recompute-all")

    assert response.status_code == 200
    payload = response.json()
    assert payload["releases_total"] == 2
    assert payload["releases_recomputed"] == 1
    assert payload["releases_failed"] == 1
    assert len(payload["errors"]) == 1
    assert payload["errors"][0]["release_id"] == "REL-2"
    assert "Synthetic recompute failure" in payload["errors"][0]["reason"]

    rel_1_metrics = client.get("/releases/REL-1/metrics").json()
    rel_2_metrics = client.get("/releases/REL-2/metrics").json()
    assert rel_1_metrics["is_computed"] is True
    assert rel_2_metrics["is_computed"] is False
