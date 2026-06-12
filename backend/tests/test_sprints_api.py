from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import Issue, IssueHistory, IssueSprint, Sprint, SprintMetricSnapshot


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


def _seed_sprint(
    session: Session,
    sprint_id: str,
    state: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> None:
    now = datetime.now(UTC)
    session.add(
        Sprint(
            sprint_id=sprint_id,
            name=f"Sprint {sprint_id}",
            state=state,
            project_key="LHPM",
            board_id="1",
            start_date=start_date or now,
            end_date=end_date or now,
            complete_date=now if state == "closed" else None,
            goal=None,
        )
    )
    session.commit()


def _seed_issue(
    session: Session,
    sprint_id: str,
    issue_key: str,
    issue_type: str = "Story",
    status: str = "Done",
    priority: str | None = "Medium",
    is_blocker: bool = False,
    story_points: float | None = None,
    created_at: datetime | None = None,
) -> None:
    session.add(
        Issue(
            issue_key=issue_key,
            summary="Example issue",
            issue_type=issue_type,
            status=status,
            priority=priority,
            assignee=None,
            story_points=story_points,
            release_id=None,
            is_blocker=is_blocker,
            created_at=created_at or datetime.now(UTC),
        )
    )
    session.add(IssueSprint(issue_key=issue_key, sprint_id=sprint_id))
    session.commit()


def _seed_sprint_snapshot(
    session: Session,
    sprint_id: str,
    snapshot_at: datetime,
    confidence: float,
    progress_alignment: float,
    velocity_fit: float,
    blocker_penalty: float = 100.0,
    scope_stability: float = 100.0,
) -> None:
    session.add(
        SprintMetricSnapshot(
            sprint_id=sprint_id,
            snapshot_at=snapshot_at,
            committed_scope=10,
            completed_scope_pct=progress_alignment,
            open_blockers=0,
            open_high_severity_bugs=0,
            bugs_created_during_sprint=0,
            open_blocker_issue_keys=[],
            open_high_severity_bug_issue_keys=[],
            bugs_created_during_sprint_issue_keys=[],
            in_progress_count=0,
            not_started_count=0,
            rollover_count=0,
            median_cycle_time_days=None,
            reopen_rate_pct=0.0,
            delivery_confidence_score=confidence,
            delivery_confidence_components={
                "progress_alignment": progress_alignment,
                "velocity_fit": velocity_fit,
                "blocker_penalty": blocker_penalty,
                "scope_stability": scope_stability,
            },
            delivery_confidence_inputs={},
        )
    )


def test_get_current_sprint_returns_active_sprint(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "11", "closed")
        _seed_sprint(session, "12", "active")

    response = client.get("/sprints/current")

    assert response.status_code == 200
    assert response.json()["item"]["sprint_id"] == "12"


def test_get_closed_sprints_filters_by_state(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "11", "closed")
        _seed_sprint(session, "12", "active")

    response = client.get("/sprints?state=closed")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["sprint_id"] == "11"


def test_recompute_and_get_sprint_metrics(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active")
        _seed_issue(session, "12", "LHPM-1")

    recompute_response = client.post("/sprints/12/recompute")
    metrics_response = client.get("/sprints/12/metrics")

    assert recompute_response.status_code == 200
    assert metrics_response.status_code == 200
    payload = metrics_response.json()
    assert payload["is_computed"] is True
    assert payload["metrics"]["committed_scope"] == 1
    assert payload["metrics"]["delivery_confidence_score"] == 100.0
    assert payload["delivery_confidence"]["score"] == 100.0
    assert payload["confidence_breakdown"]["totalScore"] == 100.0
    assert payload["biggest_driver"] == {
        "title": "No Delivery Drag",
        "category": "None",
        "impact": 0.0,
        "contributionPercent": 0.0,
        "explanation": "No delivery confidence component is currently reducing the sprint score.",
        "recommendation": "Maintain the current delivery posture and continue monitoring progress, velocity, blockers, and scope stability.",
    }
    assert payload["recommendations"] == []
    assert [component["id"] for component in payload["confidence_breakdown"]["components"]] == [
        "progress_alignment",
        "velocity_fit",
        "scope_stability",
        "blocker_health",
    ]
    assert all(component["score"] == 100.0 for component in payload["confidence_breakdown"]["components"])
    assert all(component["maxScore"] == 100.0 for component in payload["confidence_breakdown"]["components"])
    assert all(component["status"] == "good" for component in payload["confidence_breakdown"]["components"])
    assert payload["delivery_confidence"]["inputs"]["initial_commitment_count"] == 1
    assert payload["delivery_confidence"]["inputs"]["scope_stability_index"] == 0.0
    assert payload["delivery_confidence"]["inputs"]["committed_effective_points"] == 1.0
    assert payload["metric_issue_keys"] == {
        "open_blockers": [],
        "open_high_severity_bugs": [],
        "bugs_created_during_sprint": [],
    }


def test_sprint_metrics_returns_metric_issue_keys(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active", start_date=now - timedelta(days=1), end_date=now + timedelta(days=1))
        _seed_issue(session, "12", "LHPM-1", status="In Progress", is_blocker=True)
        _seed_issue(
            session,
            "12",
            "LHPM-2",
            issue_type="Bug",
            status="To Do",
            priority="Critical",
            created_at=now,
        )
        _seed_issue(
            session,
            "12",
            "LHPM-3",
            issue_type="Bug",
            status="Done",
            priority="High",
            is_blocker=True,
            created_at=now,
        )
        _seed_issue(session, "12", "LHPM-4", issue_type="Story", status="To Do", priority="High")

    recompute_response = client.post("/sprints/12/recompute")
    metrics_response = client.get("/sprints/12/metrics")

    assert recompute_response.status_code == 200
    assert metrics_response.status_code == 200
    payload = metrics_response.json()
    assert payload["metrics"]["open_blockers"] == 1
    assert payload["metrics"]["open_high_severity_bugs"] == 1
    assert payload["metrics"]["bugs_created_during_sprint"] == 2
    assert payload["metric_issue_keys"] == {
        "open_blockers": ["LHPM-1"],
        "open_high_severity_bugs": ["LHPM-2"],
        "bugs_created_during_sprint": ["LHPM-2", "LHPM-3"],
    }


def test_get_sprint_issues_returns_linked_issues(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active", start_date=now - timedelta(days=2), end_date=now + timedelta(days=2))
        _seed_issue(session, "12", "LHPM-1", story_points=5)
        _seed_issue(session, "12", "LHPM-2", story_points=3)
        session.add(
            IssueHistory(
                issue_key="LHPM-2",
                field_name="sprint",
                old_value="Sprint 11",
                new_value="Sprint 12",
                changed_at=now - timedelta(days=1),
            )
        )
        session.commit()

    response = client.get("/sprints/12/issues")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["items"][0]["story_points"] == 5.0
    assert payload["items"][0]["in_initial_scope"] is True
    assert payload["items"][1]["story_points"] == 3.0
    assert payload["items"][1]["in_initial_scope"] is False


def test_get_current_sprint_not_found(client: TestClient) -> None:
    response = client.get("/sprints/current")

    assert response.status_code == 200
    assert response.json()["item"] is None


def test_get_sprint_snapshot_comparison_uses_previous_snapshot(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active")
        base = datetime(2026, 4, 1, tzinfo=UTC)
        _seed_sprint_snapshot(session, "12", base, confidence=62.0, progress_alignment=50.0, velocity_fit=60.0)
        _seed_sprint_snapshot(session, "12", base + timedelta(hours=1), confidence=74.0, progress_alignment=70.0, velocity_fit=70.0)
        session.commit()

    response = client.get("/sprints/12/snapshot-comparison?baseline=previous")

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "12"
    assert payload["has_baseline"] is True
    assert payload["comparison"]["confidenceDelta"] == 12.0
    assert payload["comparison"]["contributors"][0]["metric"] == "progress_alignment"
    assert payload["comparison"]["contributors"][0]["impact"] == 8.0


def test_get_sprint_snapshot_change_history_returns_primary_driver(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active")
        base = datetime(2026, 4, 1, tzinfo=UTC)
        _seed_sprint_snapshot(session, "12", base, confidence=62.0, progress_alignment=50.0, velocity_fit=60.0)
        _seed_sprint_snapshot(session, "12", base + timedelta(hours=1), confidence=74.0, progress_alignment=70.0, velocity_fit=70.0)
        session.commit()

    response = client.get("/sprints/12/snapshot-change-history")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 2
    assert payload["items"][0]["primary_driver"] == "Baseline snapshot"
    assert payload["items"][1]["delta"] == 12.0
    assert payload["items"][1]["primary_driver"] == "progress_alignment"
