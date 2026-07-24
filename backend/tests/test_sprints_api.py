from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
    project_key: str = "LHPM",
) -> None:
    now = datetime.now(UTC)
    session.add(
        Sprint(
            sprint_id=sprint_id,
            name=f"Sprint {sprint_id}",
            state=state,
            project_key=project_key,
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
    issue_type: str | None = "Story",
    status: str | None = "Done",
    priority: str | None = "Medium",
    is_blocker: bool = False,
    story_points: float | None = None,
    created_at: datetime | None = None,
    has_jira_created_at: bool = True,
    jira_blocker_flag: bool | None = None,
    jira_changelog_complete: bool = True,
    assignee: str | None = None,
    jira_assignee_id: str | None = None,
) -> None:
    source_created_at = created_at or datetime.now(UTC)
    session.add(
        Issue(
            issue_key=issue_key,
            summary="Example issue",
            issue_type=issue_type,
            status=status,
            priority=priority,
            assignee=assignee,
            jira_assignee_id=jira_assignee_id,
            story_points=story_points,
            release_id=None,
            is_blocker=is_blocker,
            jira_blocker_flag=(
                jira_blocker_flag
                if jira_blocker_flag is not None
                else True if is_blocker else None
            ),
            jira_created_at=source_created_at if has_jira_created_at else None,
            jira_changelog_complete=jira_changelog_complete,
            created_at=source_created_at,
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
    delivery_confidence_status: str = "COMPUTED",
    ruleset_version: int = 1,
    classification: dict[str, object] | None = None,
) -> None:
    calculation_provenance: dict[str, object] = {
        "weights": {
            "progress_alignment": 0.4,
            "velocity_fit": 0.3,
            "blocker_penalty": 0.2,
            "scope_stability": 0.1,
        },
        "component_outputs": {},
    }
    if classification is not None:
        calculation_provenance["classification"] = classification

    session.add(
        SprintMetricSnapshot(
            sprint_id=sprint_id,
            snapshot_at=snapshot_at,
            ruleset_version=ruleset_version,
            calculation_provenance=calculation_provenance,
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
            story_point_total_count=10,
            story_point_pointed_count=10 if delivery_confidence_status == "COMPUTED" else 0,
            story_point_unpointed_count=0 if delivery_confidence_status == "COMPUTED" else 10,
            story_point_coverage_pct=100.0 if delivery_confidence_status == "COMPUTED" else 0.0,
            story_point_unpointed_issue_keys=[],
            delivery_confidence_status=delivery_confidence_status,
            delivery_confidence_explanations=[],
        )
    )


def test_get_current_sprint_returns_active_sprint(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "11", "closed")
        _seed_sprint(session, "12", "active")

    response = client.get("/sprints/current")

    assert response.status_code == 200
    assert response.json()["item"]["sprint_id"] == "12"


def test_get_current_sprint_filters_by_project_key(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active", start_date=now - timedelta(days=2), project_key="LHPM")
        _seed_sprint(session, "99", "active", start_date=now, project_key="OTHER")

    response = client.get("/sprints/current?project_key=LHPM")

    assert response.status_code == 200
    payload = response.json()
    assert payload["item"]["sprint_id"] == "12"
    assert payload["item"]["project_key"] == "LHPM"


def test_get_closed_sprints_filters_by_state(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "11", "closed")
        _seed_sprint(session, "12", "active")

    response = client.get("/sprints?state=closed")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["sprint_id"] == "11"


def test_get_sprints_filters_by_project_key(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "11", "closed", project_key="LHPM")
        _seed_sprint(session, "99", "closed", project_key="OTHER")

    response = client.get("/sprints?state=closed&project_key=LHPM")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["sprint_id"] == "11"
    assert payload["items"][0]["project_key"] == "LHPM"


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
    assert payload["metrics"]["rollover_count"] is None
    assert payload["metric_availability"]["metrics"]["rollover_count"]["status"] == "NOT_APPLICABLE"
    assert payload["computation_status"] == "PARTIAL"
    assert payload["unavailable_reason"] == "Delivery confidence requires at least 50% of sprint tickets to have valid story points."
    assert payload["metric_availability"]["context"] == {
        "has_tickets": True,
        "has_story_points": False,
        "has_completed_tickets": True,
        "has_release_scope": False,
        "has_sprint_scope": True,
        "has_changelog": False,
    }
    assert payload["metric_availability"]["metrics"]["delivery_confidence_score"] == {
        "status": "NOT_COMPUTED",
        "available": False,
        "reason": "Delivery confidence requires at least 50% of sprint tickets to have valid story points.",
        "explanations": [
            "Delivery confidence requires at least 50% of sprint tickets to have valid story points."
        ],
        "missing_issue_keys": [],
        "depends_on": [
            "ticket_count",
            "story_points",
            "ticket_status",
            "blocker_classification",
            "sprint_duration",
            "project_changelog_completeness",
            "sprint_assignment",
        ],
    }
    assert payload["metric_availability"]["metrics"]["median_cycle_time_days"] == {
        "status": "NOT_COMPUTED",
        "available": False,
        "reason": (
            "Median cycle time is not computed because complete evidence contains no valid "
            "in-progress-to-done transition pair."
        ),
        "explanations": [
            "Median cycle time is not computed because complete evidence contains no valid "
            "in-progress-to-done transition pair."
        ],
        "missing_issue_keys": [],
        "depends_on": ["ticket_count", "completed_tickets", "history_changelog", "sprint_assignment"],
    }
    assert payload["metrics"]["committed_scope"] == 1
    assert payload["metrics"]["completed_scope_pct"] == 100.0
    assert payload["metrics"]["reopen_rate_pct"] == 0.0
    assert payload["metric_availability"]["metrics"]["reopen_rate_pct"]["status"] == "COMPUTED"
    assert payload["metrics"]["delivery_confidence_score"] is None
    assert payload["delivery_confidence_status"] == "INCONCLUSIVE"
    assert payload["story_point_coverage"] == {
        "total_ticket_count": 1,
        "pointed_ticket_count": 0,
        "unpointed_ticket_count": 1,
        "coverage_pct": 0.0,
        "unpointed_issue_keys": ["LHPM-1"],
    }
    assert "fewer than 50%" in payload["delivery_confidence_explanations"][0]
    assert payload["delivery_confidence"] is None
    assert payload["confidence_breakdown"] is None
    assert payload["biggest_driver"] is None


def test_sprint_metrics_withhold_confidence_when_duration_is_missing(
    client: TestClient,
) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "duration-missing", "active")
        sprint = session.scalar(
            select(Sprint).where(Sprint.sprint_id == "duration-missing")
        )
        assert sprint is not None
        sprint.end_date = None
        session.commit()
        _seed_issue(
            session,
            "duration-missing",
            "LHPM-1",
            story_points=3,
        )

    assert client.post("/sprints/duration-missing/recompute").status_code == 200
    response = client.get("/sprints/duration-missing/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["delivery_confidence_status"] == "INCONCLUSIVE"
    assert payload["metrics"]["delivery_confidence_score"] is None
    assert payload["delivery_confidence"] is None
    assert payload["confidence_breakdown"] is None
    assert payload["biggest_driver"] is None
    assert any(
        "sprint duration is missing its end time" in explanation
        for explanation in payload["delivery_confidence_explanations"]
    )
    availability = payload["metric_availability"]["metrics"][
        "delivery_confidence_score"
    ]
    assert availability["status"] == "NOT_COMPUTED"
    assert availability["available"] is False
    assert "sprint duration is missing its end time" in availability["reason"]


def test_sprint_metrics_expose_authoritative_workload_distribution(
    client: TestClient,
) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "workload", "active")
        _seed_issue(
            session,
            "workload",
            "LHPM-1",
            status="To Do",
            story_points=6,
            assignee="Ava",
            jira_assignee_id="jira-ava",
        )
        _seed_issue(
            session,
            "workload",
            "LHPM-2",
            status="In Progress",
            story_points=4,
            assignee="Noah",
            jira_assignee_id="jira-noah",
        )

    assert client.post("/sprints/workload/recompute").status_code == 200
    response = client.get("/sprints/workload/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["workload_concentration_pct"] == 60.0
    assert payload["workload_distribution"]["status"] == "COMPUTED"
    assert payload["workload_distribution"]["percentage"] == 60.0
    assert payload["workload_distribution"]["evidence"]["risk_band"] == "critical"
    assert payload["workload_distribution"]["evidence"]["top_assignee"] == {
        "assignee_key": "jira:jira-ava",
        "assignee": "Ava",
        "story_points": 6.0,
        "issue_keys": ["LHPM-1"],
    }
    availability = payload["metric_availability"]["metrics"][
        "workload_concentration_pct"
    ]
    assert availability["status"] == "COMPUTED"
    assert availability["available"] is True
    workload_recommendation = next(
        item
        for item in payload["recommendations"]
        if item["title"] == "Reduce workload concentration"
    )
    assert workload_recommendation["dataStatus"] == "COMPUTED"
    assert workload_recommendation["explanations"] == []


def test_recomputed_empty_sprint_scope_returns_null_metrics(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active")

    recompute_response = client.post("/sprints/12/recompute")
    metrics_response = client.get("/sprints/12/metrics")

    assert recompute_response.status_code == 200
    assert metrics_response.status_code == 200
    payload = metrics_response.json()
    assert payload["metrics"]["committed_scope"] is None
    assert payload["metrics"]["completed_scope_pct"] is None
    assert payload["metrics"]["in_progress_count"] is None
    assert payload["metrics"]["not_started_count"] is None
    assert payload["metrics"]["rollover_count"] is None
    assert payload["metric_availability"]["metrics"]["committed_scope"]["status"] == "NOT_COMPUTED"
    assert payload["metric_availability"]["metrics"]["completed_scope_pct"]["status"] == "NOT_COMPUTED"
    assert payload["metric_availability"]["metrics"]["in_progress_count"]["status"] == "NOT_COMPUTED"
    assert payload["metric_availability"]["metrics"]["not_started_count"]["status"] == "NOT_COMPUTED"
    assert payload["metric_availability"]["metrics"]["rollover_count"]["status"] == "NOT_APPLICABLE"
    assert payload["calculation_provenance"]["metric_evidence"]["committed_scope"] == {
        "current_scope_issue_keys": [],
        "current_scope_count": 0,
    }


def test_missing_sprint_status_returns_partial_completed_scope(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active")
        _seed_issue(session, "12", "LHPM-1", status="Done")
        _seed_issue(session, "12", "LHPM-2", status=None)

    recompute_response = client.post("/sprints/12/recompute")
    metrics_response = client.get("/sprints/12/metrics")

    assert recompute_response.status_code == 200
    assert metrics_response.status_code == 200
    payload = metrics_response.json()
    assert payload["metrics"]["committed_scope"] == 2
    assert payload["metrics"]["completed_scope_pct"] is None
    assert payload["metrics"]["in_progress_count"] == 0
    assert payload["metrics"]["not_started_count"] == 0
    assert payload["metrics"]["rollover_count"] is None
    assert payload["metric_availability"]["metrics"]["committed_scope"]["status"] == "COMPUTED"
    completed_availability = payload["metric_availability"]["metrics"]["completed_scope_pct"]
    assert completed_availability["status"] == "PARTIAL"
    assert completed_availability["available"] is False
    assert completed_availability["missing_issue_keys"] == ["LHPM-2"]
    assert payload["metric_availability"]["metrics"]["in_progress_count"]["status"] == "PARTIAL"
    assert payload["metric_availability"]["metrics"]["in_progress_count"]["available"] is True
    assert payload["metric_availability"]["metrics"]["not_started_count"]["status"] == "PARTIAL"
    assert payload["metric_availability"]["metrics"]["rollover_count"]["status"] == "NOT_APPLICABLE"
    assert payload["calculation_provenance"]["metric_evidence"]["completed_scope_pct"][
        "completed_issue_keys"
    ] == ["LHPM-1"]
    assert payload["recommendations"] == []
    recommendation_text = " ".join(
        f"{item['title']} {item['description']}".lower() for item in payload["recommendations"]
    )
    assert "velocity" not in recommendation_text
    assert "predictability" not in recommendation_text
    assert payload["metric_issue_keys"] == {
        "open_blockers": [],
        "open_high_severity_bugs": [],
        "bugs_created_during_sprint": [],
        "bugs_created_during_sprint_missing_created_at": [],
    }


def test_get_sprint_metrics_suppresses_legacy_confidence_without_story_points(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active")
        _seed_issue(session, "12", "LHPM-1", story_points=None)
        _seed_sprint_snapshot(
            session=session,
            sprint_id="12",
            snapshot_at=datetime.now(UTC),
            confidence=72.0,
            progress_alignment=80.0,
            velocity_fit=65.0,
            delivery_confidence_status="INCONCLUSIVE",
        )
        session.commit()

    response = client.get("/sprints/12/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_computed"] is True
    assert payload["computation_status"] == "PARTIAL"
    assert payload["unavailable_reason"] == "Delivery confidence requires at least 50% of sprint tickets to have valid story points."
    assert payload["metric_availability"]["context"]["has_story_points"] is False
    assert payload["metrics"]["committed_scope"] == 10
    assert payload["metrics"]["delivery_confidence_score"] is None
    assert payload["delivery_confidence"] is None
    assert payload["confidence_breakdown"] is None
    assert payload["biggest_driver"] is None
    recommendation_text = " ".join(
        f"{item['title']} {item['description']}".lower() for item in payload["recommendations"]
    )
    assert "velocity" not in recommendation_text
    assert "predictability" not in recommendation_text


def test_get_sprint_metrics_returns_availability_when_snapshot_missing(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active")

    response = client.get("/sprints/12/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_computed"] is False
    assert payload["computation_status"] == "NOT_COMPUTED"
    assert payload["unavailable_reason"] == "No tickets are available for this scope."
    assert payload["metric_availability"]["context"] == {
        "has_tickets": False,
        "has_story_points": False,
        "has_completed_tickets": False,
        "has_release_scope": False,
        "has_sprint_scope": False,
        "has_changelog": False,
    }
    assert payload["metric_availability"]["metrics"]["committed_scope"] == {
        "status": "NOT_COMPUTED",
        "available": False,
        "reason": "No tickets are available for this scope.",
        "explanations": ["No tickets are available for this scope."],
        "missing_issue_keys": [],
        "depends_on": ["ticket_count", "sprint_assignment"],
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
    assert payload["metrics"]["open_blockers"] == 2
    assert payload["metrics"]["open_high_severity_bugs"] == 1
    assert payload["metrics"]["bugs_created_during_sprint"] == 2
    assert payload["bugs_created_during_sprint_status"] == "COMPUTED"
    assert payload["metric_issue_keys"] == {
        "open_blockers": ["LHPM-1", "LHPM-2"],
        "open_high_severity_bugs": ["LHPM-2"],
        "bugs_created_during_sprint": ["LHPM-2", "LHPM-3"],
        "bugs_created_during_sprint_missing_created_at": [],
    }


def test_sprint_blocker_and_high_severity_counts_are_partial_confirmed_minima(
    client: TestClient,
) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active")
        _seed_issue(
            session,
            "12",
            "LHPM-1",
            issue_type="Story",
            status="To Do",
            priority=None,
        )
        _seed_issue(
            session,
            "12",
            "LHPM-2",
            issue_type=None,
            status="To Do",
            priority="Medium",
            jira_blocker_flag=False,
        )

    assert client.post("/sprints/12/recompute").status_code == 200
    payload = client.get("/sprints/12/metrics").json()

    assert payload["computation_status"] == "PARTIAL"
    assert payload["metrics"]["open_blockers"] == 0
    assert payload["metrics"]["open_high_severity_bugs"] == 0
    assert payload["metric_availability"]["metrics"]["open_blockers"]["status"] == "PARTIAL"
    assert payload["metric_availability"]["metrics"]["open_blockers"][
        "missing_issue_keys"
    ] == ["LHPM-1"]
    assert payload["metric_availability"]["metrics"]["open_high_severity_bugs"][
        "missing_issue_keys"
    ] == ["LHPM-2"]
    assert payload["calculation_provenance"]["metric_evidence"]["open_blockers"][
        "indeterminate_blocker_issue_keys"
    ] == ["LHPM-1"]


def test_sprint_bug_count_is_partial_when_jira_created_time_is_missing(client: TestClient) -> None:
    now = datetime.now(UTC)
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active", start_date=now - timedelta(days=1), end_date=now + timedelta(days=1))
        _seed_issue(session, "12", "LHPM-1", issue_type="Bug", created_at=now)
        _seed_issue(
            session,
            "12",
            "LHPM-2",
            issue_type="Bug",
            created_at=now,
            has_jira_created_at=False,
        )

    recompute_response = client.post("/sprints/12/recompute")
    response = client.get("/sprints/12/metrics")

    assert recompute_response.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["bugs_created_during_sprint"] == 1
    assert payload["bugs_created_during_sprint_status"] == "PARTIAL"
    assert payload["metric_issue_keys"]["bugs_created_during_sprint"] == ["LHPM-1"]
    assert payload["metric_issue_keys"]["bugs_created_during_sprint_missing_created_at"] == ["LHPM-2"]


def test_sprint_bug_count_is_not_computed_without_sprint_start(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active")
        sprint = session.scalar(select(Sprint).where(Sprint.sprint_id == "12"))
        assert sprint is not None
        sprint.start_date = None
        _seed_issue(session, "12", "LHPM-1", issue_type="Bug")

    recompute_response = client.post("/sprints/12/recompute")
    response = client.get("/sprints/12/metrics")

    assert recompute_response.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["bugs_created_during_sprint"] is None
    assert payload["bugs_created_during_sprint_status"] == "NOT_COMPUTED"
    assert payload["metric_issue_keys"]["bugs_created_during_sprint"] == []


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
        _seed_issue(session, "12", "LHPM-1", story_points=3.0)
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


def test_sprint_comparison_is_unavailable_across_ruleset_boundary(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active")
        _seed_issue(session, "12", "LHPM-1", story_points=3.0)
        base = datetime(2026, 4, 1, tzinfo=UTC)
        _seed_sprint_snapshot(
            session, "12", base, confidence=62.0, progress_alignment=50.0, velocity_fit=60.0,
            ruleset_version=0,
        )
        _seed_sprint_snapshot(
            session, "12", base + timedelta(hours=1), confidence=74.0, progress_alignment=70.0,
            velocity_fit=70.0, ruleset_version=1,
        )
        session.commit()

    comparison = client.get("/sprints/12/snapshot-comparison?baseline=previous").json()
    history = client.get("/sprints/12/snapshot-change-history").json()

    assert comparison["comparison"]["confidenceDelta"] is None
    assert comparison["unavailable_reason"] == "Snapshot comparison unavailable because ruleset versions differ."
    assert history["items"][1]["version_boundary"] is True


def test_sprint_comparison_is_unavailable_when_classifications_differ(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active")
        _seed_issue(session, "12", "LHPM-1", story_points=3.0)
        base = datetime(2026, 4, 1, tzinfo=UTC)
        _seed_sprint_snapshot(
            session,
            "12",
            base,
            confidence=62.0,
            progress_alignment=50.0,
            velocity_fit=60.0,
            classification={"done_statuses": ["done"]},
        )
        _seed_sprint_snapshot(
            session,
            "12",
            base + timedelta(hours=1),
            confidence=74.0,
            progress_alignment=70.0,
            velocity_fit=70.0,
            classification={"done_statuses": ["released"]},
        )
        session.commit()

    comparison = client.get("/sprints/12/snapshot-comparison?baseline=previous").json()
    history = client.get("/sprints/12/snapshot-change-history").json()

    expected_reason = "Snapshot comparison unavailable because Jira classification mappings differ."
    assert comparison["comparison"]["confidenceDelta"] is None
    assert comparison["unavailable_reason"] == expected_reason
    assert history["items"][1]["primary_driver"] == "Classification boundary"
    assert history["items"][1]["comparison_unavailable_reason"] == expected_reason


def test_get_sprint_snapshot_comparison_is_unavailable_without_story_points(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active")
        _seed_issue(session, "12", "LHPM-1", story_points=None)
        base = datetime(2026, 4, 1, tzinfo=UTC)
        _seed_sprint_snapshot(
            session, "12", base, confidence=62.0, progress_alignment=50.0, velocity_fit=60.0,
            delivery_confidence_status="INCONCLUSIVE",
        )
        _seed_sprint_snapshot(
            session, "12", base + timedelta(hours=1), confidence=74.0, progress_alignment=70.0, velocity_fit=70.0,
            delivery_confidence_status="INCONCLUSIVE",
        )
        session.commit()

    response = client.get("/sprints/12/snapshot-comparison?baseline=previous")

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "12"
    assert payload["has_baseline"] is True
    assert payload["comparison"]["confidenceDelta"] is None
    assert payload["comparison"]["contributors"] == []


def test_get_sprint_snapshot_change_history_returns_primary_driver(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active")
        _seed_issue(session, "12", "LHPM-1", story_points=3.0)
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


def test_get_sprint_snapshot_change_history_is_unavailable_without_story_points(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_sprint(session, "12", "active")
        _seed_issue(session, "12", "LHPM-1", story_points=None)
        base = datetime(2026, 4, 1, tzinfo=UTC)
        _seed_sprint_snapshot(
            session, "12", base, confidence=62.0, progress_alignment=50.0, velocity_fit=60.0,
            delivery_confidence_status="INCONCLUSIVE",
        )
        _seed_sprint_snapshot(
            session, "12", base + timedelta(hours=1), confidence=74.0, progress_alignment=70.0, velocity_fit=70.0,
            delivery_confidence_status="INCONCLUSIVE",
        )
        session.commit()

    response = client.get("/sprints/12/snapshot-change-history")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 2
    assert payload["items"][0]["confidence"] is None
    assert payload["items"][0]["delta"] is None
    assert payload["items"][0]["primary_driver"] == "Not available"
    assert payload["items"][1]["confidence"] is None
    assert payload["items"][1]["delta"] is None
    assert payload["items"][1]["primary_driver"] == "Not available"
