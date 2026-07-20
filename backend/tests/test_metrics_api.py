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
from app.services.analytics_service import AnalyticsService
from app.services.signal_service import SignalService


RELEASE_CHART_METRIC_NAMES = [
    "open_blockers",
    "open_high_severity_bugs",
    "scope_completed_pct",
    "completed_tickets",
    "scope_churn_7d_pct",
    "scope_added_7d_count",
    "scope_removed_7d_count",
    "median_cycle_time_days",
    "reopen_rate_pct",
    "confidence_score",
    "gates_passed_count",
    "readiness_pct",
]


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


def _seed_issue(
    session: Session,
    issue_key: str,
    release_id: str | None,
    status: str | None,
    is_blocker: bool = False,
    issue_type: str | None = "Bug",
    priority: str | None = "High",
    story_points: float | None = None,
    jira_blocker_flag: bool | None = None,
    jira_changelog_complete: bool = True,
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
            release_id=release_id,
            is_blocker=is_blocker,
            jira_blocker_flag=(
                jira_blocker_flag
                if jira_blocker_flag is not None
                else True if is_blocker else None
            ),
            story_points=story_points,
            jira_changelog_complete=jira_changelog_complete,
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
    completed_tickets: int | None = None,
    ruleset_version: int = 1,
    classification: dict[str, object] | None = None,
) -> None:
    confidence_score = SignalService._compute_release_confidence_score(
        open_blockers=open_blockers,
        open_high_severity_bugs=open_blockers,
        scope_churn_7d_pct=float(open_blockers),
        reopen_rate_pct=float(open_blockers),
        median_cycle_time_days=float(open_blockers),
    )
    readiness = SignalService._build_release_readiness_details(
        signal=None,
        open_blockers=open_blockers,
        open_high_severity_bugs=open_blockers,
        scope_churn_7d_pct=float(open_blockers),
        reopen_rate_pct=float(open_blockers),
        median_cycle_time_days=float(open_blockers),
    )
    gates = readiness["release_gates"]
    calculation_provenance: dict[str, object] = {
        "thresholds": {
            "open_blockers_red": 0,
            "open_high_severity_bugs_red": 1,
            "open_high_severity_bugs_yellow": 0,
            "scope_churn_7d_pct_red": 20.0,
            "scope_churn_7d_pct_yellow": 10.0,
            "reopen_rate_pct_red": 15.0,
            "reopen_rate_pct_yellow": 10.0,
            "median_cycle_time_days_yellow": 7.0,
        },
        "component_outputs": {
            "risk_points": SignalService._compute_release_risk_points(
                open_blockers=open_blockers,
                open_high_severity_bugs=open_blockers,
                scope_churn_7d_pct=float(open_blockers),
                reopen_rate_pct=float(open_blockers),
                median_cycle_time_days=float(open_blockers),
            ),
            "release_gates": gates,
            "readiness_pct": round(100 * sum(1 for gate in gates if gate["passed"]) / len(gates), 2),
        },
    }
    if classification is not None:
        calculation_provenance["classification"] = classification

    session.add(
        MetricSnapshot(
            release_id=release_id,
            snapshot_at=snapshot_at,
            ruleset_version=ruleset_version,
            confidence_score=confidence_score if ruleset_version > 0 else None,
            confidence_status="COMPUTED" if ruleset_version > 0 else None,
            calculation_provenance=calculation_provenance,
            open_blockers=open_blockers,
            open_high_severity_bugs=open_blockers,
            scope_completed_pct=float(open_blockers),
            completed_tickets=completed_tickets,
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
    assert payload["computation_status"] == "NOT_COMPUTED"
    assert payload["unavailable_reason"] == "No tickets are available for this scope."
    assert payload["metric_names"] == [
        "open_blockers",
        "open_high_severity_bugs",
        "scope_completed_pct",
        "completed_tickets",
        "scope_churn_7d_pct",
        "scope_added_7d_count",
        "scope_removed_7d_count",
        "median_cycle_time_days",
        "reopen_rate_pct",
    ]
    assert payload["metric_thresholds"] is None
    assert payload["confidence_score"] is None
    assert payload["confidence_breakdown"] is None
    assert payload["biggest_driver"] is None
    assert payload["recommendations"] == []
    assert payload["is_computed"] is False
    assert payload["snapshot_age_hours"] is None
    assert payload["metric_availability"]["context"] == {
        "has_tickets": False,
        "has_story_points": False,
        "has_completed_tickets": False,
        "has_release_scope": False,
        "has_sprint_scope": False,
        "has_changelog": False,
    }
    assert payload["metric_availability"]["metrics"]["scope_completed_pct"] == {
        "status": "NOT_COMPUTED",
        "available": False,
        "reason": "No tickets are available for this scope.",
        "explanations": ["No tickets are available for this scope."],
        "missing_issue_keys": [],
        "depends_on": ["ticket_count", "release_assignment"],
    }
    assert payload["metric_issue_keys"] == {
        "open_blockers": [],
        "open_high_severity_bugs": [],
        "completed_tickets": [],
    }
    assert payload["metrics"] == {
        "open_blockers": None,
        "open_high_severity_bugs": None,
        "scope_completed_pct": None,
        "completed_tickets": None,
        "scope_churn_7d_pct": None,
        "scope_added_7d_count": None,
        "scope_removed_7d_count": None,
        "median_cycle_time_days": None,
        "reopen_rate_pct": None,
    }


def test_get_release_metrics_suppresses_confidence_for_zero_ticket_snapshot(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_snapshot(
            session=session,
            release_id="REL-1",
            snapshot_at=datetime.now(UTC),
            open_blockers=0,
            completed_tickets=0,
        )
        session.commit()

    response = client.get("/releases/REL-1/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["is_computed"] is True
    assert payload["computation_status"] == "NOT_COMPUTED"
    assert payload["unavailable_reason"] == "No tickets are available for this scope."
    assert payload["confidence_score"] is None
    assert payload["confidence_breakdown"] is None
    assert payload["biggest_driver"] is None
    assert payload["recommendations"] == []
    assert payload["metric_availability"]["context"]["has_tickets"] is False
    assert payload["metric_availability"]["metrics"]["confidence_score"] == {
        "status": "NOT_COMPUTED",
        "available": False,
        "reason": "No tickets are available for this scope.",
        "explanations": ["No tickets are available for this scope."],
        "missing_issue_keys": [],
        "depends_on": ["ticket_count", "release_assignment"],
    }


def test_get_release_charts_returns_empty_series_when_snapshot_missing(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")

    response = client.get("/releases/REL-1/charts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["release_id"] == "REL-1"
    assert payload["metric_names"] == RELEASE_CHART_METRIC_NAMES
    assert payload["point_count"] == 0
    assert payload["release_gates_total"] == 0
    assert payload["series"] == {
        "open_blockers": [],
        "open_high_severity_bugs": [],
        "scope_completed_pct": [],
        "completed_tickets": [],
        "scope_churn_7d_pct": [],
        "scope_added_7d_count": [],
        "scope_removed_7d_count": [],
        "median_cycle_time_days": [],
        "reopen_rate_pct": [],
        "confidence_score": [],
        "gates_passed_count": [],
        "readiness_pct": [],
    }


def test_recompute_empty_release_suppresses_confidence_outputs(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-EMPTY")

    recompute = client.post("/releases/REL-EMPTY/recompute")
    metrics_response = client.get("/releases/REL-EMPTY/metrics")
    charts_response = client.get("/releases/REL-EMPTY/charts")
    signal_response = client.get("/releases/REL-EMPTY/signal")

    assert recompute.status_code == 200
    assert metrics_response.status_code == 200
    metrics = metrics_response.json()
    assert metrics["is_computed"] is True
    assert metrics["computation_status"] == "NOT_COMPUTED"
    assert metrics["unavailable_reason"] == "No tickets are available for this scope."
    assert metrics["confidence_score"] is None
    assert metrics["metrics"]["scope_completed_pct"] is None
    assert metrics["metric_availability"]["context"]["has_tickets"] is False
    assert metrics["confidence_breakdown"] is None
    assert metrics["biggest_driver"] is None
    assert metrics["recommendations"] == []

    assert charts_response.status_code == 200
    charts = charts_response.json()
    assert charts["release_gates_total"] == 0
    assert charts["series"]["confidence_score"][0]["value"] is None
    assert charts["series"]["gates_passed_count"][0]["value"] is None
    assert charts["series"]["readiness_pct"][0]["value"] is None

    assert signal_response.status_code == 200
    signal = signal_response.json()
    assert signal["signal"] is None
    assert signal["status_label"] == "NOT COMPUTED"
    assert signal["confidence_score"] is None
    assert signal["summary"] == "Release signal is not computed because no tickets are assigned to this release."
    assert signal["reasons"] == ["No tickets are assigned to this release."]


def test_recompute_release_metrics_creates_snapshot(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1", name="Release 1")
        _seed_issue(session, "LHPM-1", "REL-1", "In Progress", is_blocker=True)
        _seed_issue(session, "LHPM-2", "REL-1", "Done", is_blocker=False, story_points=3.0)
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
    assert metrics["computation_status"] == "COMPUTED"
    assert metrics["unavailable_reason"] is None
    assert metrics["confidence_score"] == 55.0
    assert isinstance(metrics["snapshot_age_hours"], float)
    assert metrics["snapshot_age_hours"] >= 0.0
    assert metrics["metric_names"] == [
        "open_blockers",
        "open_high_severity_bugs",
        "scope_completed_pct",
        "completed_tickets",
        "scope_churn_7d_pct",
        "scope_added_7d_count",
        "scope_removed_7d_count",
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
    assert metrics["metric_availability"]["context"] == {
        "has_tickets": True,
        "has_story_points": True,
        "has_completed_tickets": True,
        "has_release_scope": True,
        "has_sprint_scope": False,
        "has_changelog": True,
    }
    assert metrics["metric_availability"]["metrics"]["median_cycle_time_days"] == {
        "status": "COMPUTED",
        "available": True,
        "reason": None,
        "explanations": [],
        "missing_issue_keys": [],
        "depends_on": ["ticket_count", "completed_tickets", "history_changelog", "release_assignment"],
    }
    assert metrics["metric_availability"]["metrics"]["scope_churn_7d_pct"] == {
        "status": "COMPUTED",
        "available": True,
        "reason": None,
        "explanations": [],
        "missing_issue_keys": [],
        "depends_on": ["project_changelog_completeness", "observed_release_scope"],
    }
    assert metrics["confidence_breakdown"] == {
        "totalScore": 55.0,
        "components": [
            {
                "id": "delivery",
                "name": "Delivery",
                "score": 14.0,
                "maxScore": 30.0,
                "status": "critical",
                "explanation": "Open blockers and Scope churn above the red threshold are reducing delivery confidence.",
            },
            {
                "id": "quality",
                "name": "Quality",
                "score": 21.0,
                "maxScore": 30.0,
                "status": "critical",
                "explanation": "1 open high-severity bug is reducing quality confidence.",
            },
            {
                "id": "flow",
                "name": "Flow",
                "score": 20.0,
                "maxScore": 20.0,
                "status": "good",
                "explanation": "Median cycle time is within the flow confidence threshold.",
            },
            {
                "id": "risk",
                "name": "Risk",
                "score": 0.0,
                "maxScore": 20.0,
                "status": "critical",
                "explanation": "1 open blocker issue is consuming release risk capacity.",
            },
        ],
    }
    assert metrics["biggest_driver"] == {
        "title": "Open Blockers",
        "category": "Risk",
        "impact": -28.0,
        "contributionPercent": 62.2,
        "explanation": "Open blockers are consuming the largest share of release confidence.",
        "recommendation": "Resolve or explicitly de-scope blocker tickets before moving the release forward.",
    }
    assert metrics["recommendations"] == [
        {
            "title": "Resolve blockers",
            "description": "Resolve or explicitly de-scope open blocker tickets before moving the release forward.",
            "priority": 1,
            "confidenceImpact": 10,
            "effort": "high",
            "category": "Risk",
            "dataStatus": "COMPUTED",
            "explanations": [],
        },
        {
            "title": "Resolve critical defects",
            "description": "Prioritize high-severity defect fixes and verify them before release approval.",
            "priority": 2,
            "confidenceImpact": 8,
            "effort": "medium",
            "category": "Quality",
            "dataStatus": "COMPUTED",
            "explanations": [],
        },
        {
            "title": "Stabilize release scope",
            "description": "Stop non-critical fix-version movement and defer new scope to a later release.",
            "priority": 3,
            "confidenceImpact": 7,
            "effort": "medium",
            "category": "Delivery",
            "dataStatus": "COMPUTED",
            "explanations": [],
        },
    ]
    assert metrics["metrics"]["open_blockers"] == 1
    assert metrics["metrics"]["open_high_severity_bugs"] == 1
    assert metrics["metrics"]["scope_completed_pct"] == 50.0
    assert metrics["metrics"]["completed_tickets"] == 1
    assert metrics["metrics"]["scope_churn_7d_pct"] == 50.0
    assert metrics["metrics"]["scope_added_7d_count"] == 1
    assert metrics["metrics"]["scope_removed_7d_count"] == 0
    assert metrics["metrics"]["reopen_rate_pct"] == 0.0
    assert metrics["metric_issue_keys"] == {
        "open_blockers": ["LHPM-1"],
        "open_high_severity_bugs": ["LHPM-1"],
        "completed_tickets": ["LHPM-2"],
    }

    charts = client.get("/releases/REL-1/charts")
    assert charts.status_code == 200
    charts_payload = charts.json()
    assert charts_payload["metric_names"] == RELEASE_CHART_METRIC_NAMES
    assert charts_payload["point_count"] == 1
    assert charts_payload["release_gates_total"] == 5
    series = charts_payload["series"]
    assert len(series["open_blockers"]) == 1
    assert series["open_blockers"][0]["value"] == 1
    assert len(series["scope_completed_pct"]) == 1
    assert series["scope_completed_pct"][0]["value"] == 50.0
    assert len(series["completed_tickets"]) == 1
    assert series["completed_tickets"][0]["value"] == 1
    assert len(series["scope_added_7d_count"]) == 1
    assert series["scope_added_7d_count"][0]["value"] == 1
    assert len(series["scope_removed_7d_count"]) == 1
    assert series["scope_removed_7d_count"][0]["value"] == 0
    assert len(series["confidence_score"]) == 1
    assert series["confidence_score"][0]["value"] == 55.0
    assert len(series["gates_passed_count"]) == 1
    assert series["gates_passed_count"][0]["value"] == 3
    assert len(series["readiness_pct"]) == 1
    assert series["readiness_pct"][0]["value"] == 60.0

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
    assert payload["metrics"]["open_blockers"] == 2
    assert payload["metrics"]["open_high_severity_bugs"] == 1
    assert payload["metric_issue_keys"] == {
            "open_blockers": ["LHPM-1", "LHPM-2"],
            "open_high_severity_bugs": ["LHPM-2"],
            "completed_tickets": ["LHPM-3"],
        }


def test_release_metrics_api_exposes_reopen_event_evidence_and_explanation(
    client: TestClient,
) -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(
            session,
            "LHPM-1",
            "REL-1",
            "In Progress",
            issue_type="Story",
            priority="Medium",
        )
        _seed_history(session, "LHPM-1", "status", "To Do", "Done", base)
        _seed_history(
            session,
            "LHPM-1",
            "status",
            "Done",
            "In Progress",
            base + timedelta(hours=1),
        )
        _seed_history(
            session,
            "LHPM-1",
            "status",
            "In Progress",
            "Done",
            base + timedelta(hours=2),
        )
        _seed_history(
            session,
            "LHPM-1",
            "status",
            "Done",
            "In Progress",
            base + timedelta(hours=3),
        )
        session.commit()

    recompute = client.post("/releases/REL-1/recompute")
    response = client.get("/releases/REL-1/metrics")
    charts = client.get("/releases/REL-1/charts")

    assert recompute.status_code == 200
    assert response.status_code == 200
    assert charts.status_code == 200
    payload = response.json()
    assert payload["metrics"]["reopen_rate_pct"] == 200.0
    availability = payload["metric_availability"]["metrics"]["reopen_rate_pct"]
    assert availability["status"] == "COMPUTED"
    assert availability["available"] is True
    assert availability["reason"] is None
    assert availability["explanations"] == [
        "Ticket LHPM-1 was counted 2 times because it was reopened 2 times."
    ]
    evidence = payload["calculation_provenance"]["metric_evidence"]["reopen_rate_pct"]
    assert evidence["eligible_ticket_count"] == 1
    assert evidence["reopen_event_count"] == 2
    assert evidence["multiple_reopen_issue_keys"] == ["LHPM-1"]
    assert charts.json()["series"]["reopen_rate_pct"][-1]["value"] == 200.0


def test_release_metric_availability_flags_missing_story_points(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(session, "LHPM-1", "REL-1", "To Do", issue_type="Story", priority="Medium")
        session.commit()

    recompute = client.post("/releases/REL-1/recompute")
    response = client.get("/releases/REL-1/metrics")

    assert recompute.status_code == 200
    assert response.status_code == 200
    availability = response.json()["metric_availability"]
    payload = response.json()
    assert payload["computation_status"] == "PARTIAL"
    assert payload["unavailable_reason"] == (
        "Median cycle time is not computed because complete evidence contains no valid "
        "in-progress-to-done transition pair."
    )
    assert payload["confidence_score"] is None
    assert availability["context"]["has_tickets"] is True
    assert availability["context"]["has_story_points"] is False
    assert availability["context"]["has_completed_tickets"] is False
    assert availability["context"]["has_release_scope"] is True
    assert availability["metrics"]["median_cycle_time_days"]["available"] is False
    assert availability["metrics"]["median_cycle_time_days"]["reason"] == (
        "Median cycle time is not computed because complete evidence contains no valid "
        "in-progress-to-done transition pair."
    )
    assert availability["metrics"]["confidence_score"] == {
        "status": "NOT_COMPUTED",
        "available": False,
        "reason": (
            "Release confidence is unavailable because required metric inputs are unavailable "
            "for: median_cycle_time_days, reopen_rate_pct."
        ),
        "explanations": [
            "Release confidence is unavailable because required metric inputs are unavailable "
            "for: median_cycle_time_days, reopen_rate_pct."
        ],
        "missing_issue_keys": [],
        "depends_on": ["ticket_count", "release_assignment"],
    }


def test_release_scope_churn_partial_keeps_confirmed_counts_and_withholds_risk_outputs(
    client: TestClient,
) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1", name="Release 1")
        _seed_issue(
            session,
            "LHPM-1",
            "REL-1",
            "To Do",
            issue_type="Story",
            priority="Medium",
            jira_blocker_flag=False,
        )
        _seed_issue(
            session,
            "LHPM-2",
            None,
            "To Do",
            issue_type="Story",
            priority="Medium",
            jira_blocker_flag=False,
            jira_changelog_complete=False,
        )
        _seed_history(
            session,
            "LHPM-2",
            "fix version",
            "Release 0",
            "Release 1",
            datetime.now(UTC) - timedelta(days=1),
        )
        session.commit()

    assert client.post("/releases/REL-1/recompute").status_code == 200
    metrics = client.get("/releases/REL-1/metrics").json()
    charts = client.get("/releases/REL-1/charts").json()
    signal = client.get("/releases/REL-1/signal").json()

    assert metrics["computation_status"] == "PARTIAL"
    assert metrics["metrics"]["scope_churn_7d_pct"] is None
    assert metrics["metrics"]["scope_added_7d_count"] == 1
    assert metrics["metrics"]["scope_removed_7d_count"] == 0
    assert metrics["confidence_score"] is None
    churn_availability = metrics["metric_availability"]["metrics"]["scope_churn_7d_pct"]
    assert churn_availability["status"] == "PARTIAL"
    assert churn_availability["available"] is False
    assert churn_availability["missing_issue_keys"] == ["LHPM-2"]
    assert churn_availability["depends_on"] == [
        "project_changelog_completeness",
        "observed_release_scope",
    ]
    assert metrics["metric_availability"]["metrics"]["scope_added_7d_count"][
        "available"
    ] is True
    evidence = metrics["calculation_provenance"]["scope_churn_7d"]
    assert evidence["synchronized_project_issue_keys"] == ["LHPM-1", "LHPM-2"]
    assert evidence["current_scope_issue_keys"] == ["LHPM-1"]
    assert evidence["observed_scope_issue_keys"] == ["LHPM-1", "LHPM-2"]
    assert evidence["observed_scope_denominator"] == 2
    assert evidence["added_issue_keys"] == ["LHPM-2"]
    assert evidence["incomplete_project_changelog_issue_keys"] == ["LHPM-2"]
    assert charts["series"]["scope_churn_7d_pct"][-1]["value"] is None
    assert charts["series"]["scope_added_7d_count"][-1]["value"] == 1
    assert signal["signal"] == "INCONCLUSIVE"
    assert signal["confidence_score"] is None
    assert all(
        gate["metric_name"] != "scope_churn_7d_pct" for gate in signal["release_gates"]
    )
    assert any("LHPM-2" in reason for reason in signal["reasons"])


def test_release_recommendations_skip_unavailable_history_metrics(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(session, "LHPM-1", "REL-1", "In Progress", is_blocker=True)
        _seed_snapshot(
            session=session,
            release_id="REL-1",
            snapshot_at=datetime.now(UTC),
            open_blockers=25,
            completed_tickets=0,
        )
        session.commit()

    response = client.get("/releases/REL-1/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["metric_availability"]["context"]["has_changelog"] is False
    assert payload["metric_availability"]["metrics"]["scope_churn_7d_pct"]["available"] is False
    assert payload["metric_availability"]["metrics"]["reopen_rate_pct"]["available"] is False
    assert payload["metric_availability"]["metrics"]["median_cycle_time_days"]["available"] is False
    assert [item["title"] for item in payload["recommendations"]] == [
        "Resolve blockers",
        "Resolve critical defects",
    ]


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


def test_get_release_snapshot_comparison_uses_previous_snapshot(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        base = datetime(2026, 4, 1, tzinfo=UTC)
        _seed_snapshot(session, "REL-1", base, open_blockers=1, completed_tickets=2)
        _seed_snapshot(session, "REL-1", base + timedelta(hours=1), open_blockers=0, completed_tickets=4)
        session.commit()

    response = client.get("/releases/REL-1/snapshot-comparison?baseline=previous")

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "REL-1"
    assert payload["baseline"] == "previous"
    assert payload["has_baseline"] is True
    assert payload["comparison"]["confidenceDelta"] == 37.0
    assert payload["comparison"]["contributors"][0] == {
        "metric": "open_blockers",
        "delta": -1.0,
        "impact": 28.0,
        "direction": "down",
    }


def test_release_classification_partial_metrics_store_complete_evidence_and_keep_confirmed_red(
    client: TestClient,
) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(
            session,
            "LHPM-1",
            "REL-1",
            "To Do",
            issue_type=None,
            priority="Medium",
            jira_blocker_flag=False,
        )
        _seed_issue(
            session,
            "LHPM-2",
            "REL-1",
            "To Do",
            issue_type="Bug",
            priority=None,
            jira_blocker_flag=False,
        )
        _seed_issue(
            session,
            "LHPM-3",
            "REL-1",
            None,
            issue_type="Bug",
            priority="Critical",
            jira_blocker_flag=False,
        )
        _seed_issue(
            session,
            "LHPM-4",
            "REL-1",
            "To Do",
            issue_type="Story",
            priority=None,
        )
        _seed_issue(
            session,
            "LHPM-5",
            "REL-1",
            "In Progress",
            is_blocker=True,
            issue_type="Story",
            priority="Medium",
        )
        session.commit()

    assert client.post("/releases/REL-1/recompute").status_code == 200
    metrics = client.get("/releases/REL-1/metrics").json()
    signal = client.get("/releases/REL-1/signal").json()
    charts = client.get("/releases/REL-1/charts").json()

    assert metrics["computation_status"] == "PARTIAL"
    assert metrics["confidence_score"] is None
    assert metrics["metrics"]["open_blockers"] == 1
    assert metrics["metrics"]["open_high_severity_bugs"] == 0
    assert metrics["metrics"]["scope_completed_pct"] is None
    assert metrics["metrics"]["completed_tickets"] == 0
    assert metrics["metric_issue_keys"]["completed_tickets"] == []
    assert metrics["metric_availability"]["metrics"]["open_blockers"] == {
        "status": "PARTIAL",
        "available": True,
        "reason": (
            "Open blockers are a confirmed minimum because blocker classification is incomplete "
            "for 2 ticket(s). Additional blockers may exist."
        ),
        "explanations": [
            "Open blockers are a confirmed minimum because blocker classification is incomplete "
            "for 2 ticket(s). Additional blockers may exist."
        ],
        "missing_issue_keys": ["LHPM-3", "LHPM-4"],
        "depends_on": ["ticket_count", "release_assignment"],
    }
    assert metrics["metric_availability"]["metrics"]["open_high_severity_bugs"][
        "missing_issue_keys"
    ] == ["LHPM-1", "LHPM-2", "LHPM-3"]
    assert metrics["metric_availability"]["metrics"]["scope_completed_pct"]["available"] is False
    assert metrics["metric_availability"]["metrics"]["completed_tickets"]["available"] is True
    assert metrics["metric_availability"]["metrics"]["confidence_score"] == {
        "status": "PARTIAL",
        "available": False,
        "reason": (
            "Release confidence is unavailable because required metric inputs are unavailable "
            "for: median_cycle_time_days, open_blockers, open_high_severity_bugs, reopen_rate_pct."
        ),
        "explanations": [
            "Release confidence is unavailable because required metric inputs are unavailable "
            "for: median_cycle_time_days, open_blockers, open_high_severity_bugs, reopen_rate_pct."
        ],
        "missing_issue_keys": ["LHPM-1", "LHPM-2", "LHPM-3", "LHPM-4"],
        "depends_on": ["ticket_count", "release_assignment"],
    }
    assert metrics["calculation_provenance"]["metric_evidence"]["open_blockers"] == {
        "evaluated_issue_keys": ["LHPM-1", "LHPM-2", "LHPM-5"],
        "matching_issue_keys": ["LHPM-5"],
        "missing_status_issue_keys": ["LHPM-3"],
        "missing_issue_type_issue_keys": [],
        "missing_severity_issue_keys": ["LHPM-4"],
        "indeterminate_blocker_issue_keys": ["LHPM-3", "LHPM-4"],
    }
    assert charts["series"]["open_blockers"][-1]["value"] == 1
    assert charts["series"]["scope_completed_pct"][-1]["value"] is None
    assert charts["series"]["completed_tickets"][-1]["value"] == 0
    assert signal["signal"] == "RED"
    assert signal["confidence_score"] is None
    assert signal["release_outlook"]["label"] == "AT RISK"
    assert any("LHPM-3, LHPM-4" in reason for reason in signal["reasons"])


def test_release_signal_is_inconclusive_without_confirmed_hard_red(
    client: TestClient,
) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(
            session,
            "LHPM-1",
            "REL-1",
            "To Do",
            issue_type="Story",
            priority=None,
        )
        session.commit()

    assert client.post("/releases/REL-1/recompute").status_code == 200
    assert client.post("/releases/REL-1/recompute").status_code == 200
    metrics = client.get("/releases/REL-1/metrics").json()
    signal = client.get("/releases/REL-1/signal").json()
    comparison = client.get("/releases/REL-1/snapshot-comparison?baseline=previous").json()
    history = client.get("/releases/REL-1/snapshot-change-history").json()

    assert metrics["computation_status"] == "PARTIAL"
    assert metrics["metrics"]["open_blockers"] == 0
    assert metrics["confidence_score"] is None
    assert signal["signal"] == "INCONCLUSIVE"
    assert signal["status_label"] == "INCONCLUSIVE"
    assert signal["confidence_score"] is None
    assert all(gate["metric_name"] != "open_blockers" for gate in signal["release_gates"])
    assert signal["release_outlook"]["label"] == "INCONCLUSIVE"
    assert signal["release_outlook"]["signal"] == "INCONCLUSIVE"
    assert any("LHPM-1" in reason for reason in signal["reasons"])
    expected_comparison_reason = (
        "Snapshot comparison unavailable because release confidence is inconclusive for one or both snapshots."
    )
    assert comparison["comparison"]["confidenceDelta"] is None
    assert comparison["unavailable_reason"] == expected_comparison_reason
    assert history["items"][1]["comparison_unavailable_reason"] == expected_comparison_reason


def test_get_release_snapshot_comparison_supports_24h_baseline(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        base = datetime(2026, 4, 1, 12, tzinfo=UTC)
        _seed_snapshot(session, "REL-1", base - timedelta(hours=25), open_blockers=1)
        _seed_snapshot(session, "REL-1", base - timedelta(hours=2), open_blockers=2)
        _seed_snapshot(session, "REL-1", base, open_blockers=0)
        session.commit()

    response = client.get("/releases/REL-1/snapshot-comparison?baseline=24h")

    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline"] == "24h"
    assert payload["has_baseline"] is True
    assert payload["comparison"]["confidenceDelta"] == 37.0


def test_get_release_snapshot_change_history_returns_primary_driver(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        base = datetime(2026, 4, 1, tzinfo=UTC)
        _seed_snapshot(session, "REL-1", base, open_blockers=1)
        _seed_snapshot(session, "REL-1", base + timedelta(hours=1), open_blockers=0)
        session.commit()

    response = client.get("/releases/REL-1/snapshot-change-history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "REL-1"
    assert len(payload["items"]) == 2
    assert payload["items"][0]["primary_driver"] == "Baseline snapshot"
    assert payload["items"][1]["delta"] == 37.0
    assert payload["items"][1]["primary_driver"] == "open_blockers"


def test_release_history_marks_ruleset_boundaries_and_blocks_cross_version_delta(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        base = datetime(2026, 4, 1, tzinfo=UTC)
        _seed_snapshot(session, "REL-1", base, open_blockers=1, ruleset_version=0)
        _seed_snapshot(session, "REL-1", base + timedelta(hours=1), open_blockers=0, ruleset_version=1)
        session.commit()

    comparison = client.get("/releases/REL-1/snapshot-comparison?baseline=previous").json()
    history = client.get("/releases/REL-1/snapshot-change-history").json()
    charts = client.get("/releases/REL-1/charts").json()

    assert comparison["comparison"]["confidenceDelta"] is None
    assert comparison["current_ruleset_version"] == 1
    assert comparison["baseline_ruleset_version"] == 0
    assert comparison["unavailable_reason"] == "Snapshot comparison unavailable because ruleset versions differ."
    assert history["items"][1]["version_boundary"] is True
    assert history["items"][1]["comparison_unavailable_reason"] == comparison["unavailable_reason"]
    assert charts["series"]["confidence_score"][0]["ruleset_version"] == 0
    assert charts["series"]["confidence_score"][0]["value"] is None
    assert charts["series"]["confidence_score"][1]["ruleset_version"] == 1
    assert charts["series"]["confidence_score"][1]["version_boundary"] is True


def test_release_comparison_is_unavailable_when_classifications_differ(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        base = datetime(2026, 4, 1, tzinfo=UTC)
        _seed_snapshot(
            session,
            "REL-1",
            base,
            open_blockers=1,
            classification={"done_statuses": ["done"]},
        )
        _seed_snapshot(
            session,
            "REL-1",
            base + timedelta(hours=1),
            open_blockers=0,
            classification={"done_statuses": ["released"]},
        )
        session.commit()

    comparison = client.get("/releases/REL-1/snapshot-comparison?baseline=previous").json()
    history = client.get("/releases/REL-1/snapshot-change-history").json()

    expected_reason = "Snapshot comparison unavailable because Jira classification mappings differ."
    assert comparison["comparison"]["confidenceDelta"] is None
    assert comparison["unavailable_reason"] == expected_reason
    assert history["items"][1]["primary_driver"] == "Classification boundary"
    assert history["items"][1]["comparison_unavailable_reason"] == expected_reason


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
