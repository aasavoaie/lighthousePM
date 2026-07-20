from collections.abc import Generator
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models import Issue, IssueHistory, MetricSnapshot, Release
from app.services.signal_service import SignalService
from app.utils.constants import RULESET_VERSION


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
    release_date: datetime | None = None,
) -> None:
    now = datetime.now(UTC)
    session.add(
        Release(
            release_id=release_id,
            name="Release 1",
            project_key="LHPM",
            description="Seed release",
            status="active",
            start_date=now,
            release_date=release_date,
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
    snapshot_at: datetime | None = None,
    open_blocker_issue_keys: list[str] | None = None,
    open_high_severity_bug_issue_keys: list[str] | None = None,
    completed_tickets: int | None = None,
) -> None:
    confidence_score = SignalService._compute_release_confidence_score(
        open_blockers=open_blockers,
        open_high_severity_bugs=open_high_severity_bugs,
        scope_churn_7d_pct=scope_churn_7d_pct,
        reopen_rate_pct=reopen_rate_pct,
        median_cycle_time_days=median_cycle_time_days,
    )
    session.add(
        MetricSnapshot(
            release_id=release_id,
            snapshot_at=snapshot_at or datetime.now(UTC),
            ruleset_version=RULESET_VERSION,
            confidence_score=confidence_score,
            confidence_status="COMPUTED",
            calculation_provenance={
                "thresholds": {
                    "open_blockers_red": 0,
                    "open_high_severity_bugs_red": 1,
                    "open_high_severity_bugs_yellow": 0,
                    "scope_churn_7d_pct_red": 20.0,
                    "scope_churn_7d_pct_yellow": 10.0,
                    "reopen_rate_pct_red": 15.0,
                    "reopen_rate_pct_yellow": 10.0,
                    "median_cycle_time_days_yellow": 7.0,
                    "confidence_score_red_max": 60.0,
                    "confidence_score_yellow_min": 61.0,
                    "confidence_score_yellow_max": 90.0,
                    "confidence_score_green_min": 91.0,
                },
                "component_outputs": {
                    "confidence_breakdown": None,
                    "biggest_driver": None,
                }
            },
            open_blockers=open_blockers,
            open_high_severity_bugs=open_high_severity_bugs,
            open_blocker_issue_keys=open_blocker_issue_keys or [],
            open_high_severity_bug_issue_keys=open_high_severity_bug_issue_keys or [],
            scope_completed_pct=50.0,
            completed_tickets=completed_tickets,
            scope_churn_7d_pct=scope_churn_7d_pct,
            median_cycle_time_days=median_cycle_time_days,
            reopen_rate_pct=reopen_rate_pct,
        )
    )
    session.commit()


def _seed_issue(
    session: Session,
    issue_key: str,
    release_id: str,
    status: str,
    is_blocker: bool,
    created_at: datetime | None = None,
    issue_type: str = "Bug",
    priority: str = "High",
) -> None:
    now = created_at or datetime.now(UTC)
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
            jira_blocker_flag=True if is_blocker else None,
            jira_created_at=now,
            jira_changelog_complete=True,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def _seed_signal(session: Session, release_id: str, signal: str) -> None:
    result = SignalService().recompute_release_signal(session, release_id)
    assert result.signal == signal
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
        "metric_snapshot_id": None,
        "ruleset_version": 0,
        "signal": None,
        "status_label": "NOT COMPUTED",
        "confidence_score": None,
        "confidence_breakdown": None,
        "biggest_driver": None,
        "summary": "Release signal is not computed because no tickets are assigned to this release.",
        "reasons": ["No tickets are assigned to this release."],
        "reason_details": [],
        "release_gates": [],
        "critical_risks": [],
        "warnings": [],
        "primary_risk": None,
        "risk_aging": {
            "blockers": {"count": 0, "known_count": 0, "unknown_count": 0, "oldest_age_days": None, "average_age_days": None, "tickets": []},
            "high_severity_bugs": {"count": 0, "known_count": 0, "unknown_count": 0, "oldest_age_days": None, "average_age_days": None, "tickets": []},
            "as_of": None,
        },
        "last_24_hours": {"as_of": None, "baseline_at": None, "has_baseline": False, "unavailable_reason": None, "items": []},
        "release_outlook": {
            "label": "NOT COMPUTED",
            "signal": None,
            "confidence_score": None,
            "snapshot_at": None,
            "release_date": None,
            "days_remaining": None,
            "passed_gate_count": 0,
            "failed_gate_count": 0,
            "release_gates": [],
            "confidence_change_24h": None,
            "confidence_baseline_at": None,
            "active_conditions": [],
            "disclaimer": "This outlook reflects the latest stored snapshot and is not a forecast.",
        },
            "thresholds": None,
            "calculated_at": None,
            "updated_at": None,
        }


def test_get_release_signal_after_metrics_recompute_uses_hard_rule_floor(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(
            session,
            issue_key="LHPM-1",
            release_id="REL-1",
            status="In Progress",
            is_blocker=True,
            issue_type="Story",
            priority="Medium",
        )

    recompute = client.post("/releases/REL-1/recompute")
    assert recompute.status_code == 200

    response = client.get("/releases/REL-1/signal")
    assert response.status_code == 200
    payload = response.json()
    assert payload["release_id"] == "REL-1"
    assert payload["signal"] == "RED"
    assert payload["status_label"] == "NOT READY FOR RELEASE"
    assert payload["confidence_score"] is None
    assert payload["confidence_breakdown"] is None
    assert payload["biggest_driver"] is None
    cycle_gate = next(
        gate
        for gate in payload["release_gates"]
        if gate["metric_name"] == "median_cycle_time_days"
    )
    assert cycle_gate["passed"] is True
    assert cycle_gate["value"] is None
    assert any(gate["metric_name"] == "open_blockers" and not gate["passed"] for gate in payload["release_gates"])
    assert any(risk["metric_name"] == "open_blockers" for risk in payload["critical_risks"])
    assert payload["risk_aging"]["blockers"]["count"] == 1
    assert any("blocker" in reason.lower() for reason in payload["reasons"])
    assert payload["thresholds"]["open_blockers_red"] == 0
    assert payload["thresholds"]["confidence_score_yellow_max"] == 90.0
    assert any(detail["metric_name"] == "open_blockers" for detail in payload["reason_details"])
    assert all(detail["message"] in payload["reasons"] for detail in payload["reason_details"])


def test_get_release_signal_after_metrics_recompute_returns_green(client: TestClient) -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(session, "LHPM-1", "REL-1", "Done", is_blocker=False, issue_type="Story", priority="Medium")
        session.add_all(
            [
                IssueHistory(
                    issue_key="LHPM-1",
                    field_name="status",
                    old_value="To Do",
                    new_value="In Progress",
                    changed_at=base,
                ),
                IssueHistory(
                    issue_key="LHPM-1",
                    field_name="status",
                    old_value="In Progress",
                    new_value="Done",
                    changed_at=base + timedelta(days=2),
                ),
            ]
        )
        session.commit()

    recompute = client.post("/releases/REL-1/recompute")
    assert recompute.status_code == 200

    response = client.get("/releases/REL-1/signal")
    assert response.status_code == 200
    payload = response.json()
    assert payload["signal"] == "GREEN"
    assert payload["status_label"] == "READY FOR RELEASE"
    assert payload["confidence_score"] == 100.0
    assert payload["confidence_breakdown"]["totalScore"] == 100.0
    assert payload["biggest_driver"] == {
        "title": "No Confidence Drag",
        "category": "None",
        "impact": 0.0,
        "contributionPercent": 0.0,
        "explanation": "No active release risk points are reducing confidence.",
        "recommendation": "Maintain release readiness by keeping blockers, quality risk, scope churn, and flow within thresholds.",
    }
    assert all(component["status"] == "good" for component in payload["confidence_breakdown"]["components"])
    assert all(gate["passed"] for gate in payload["release_gates"])
    assert payload["critical_risks"] == []
    assert payload["warnings"] == []
    assert payload["primary_risk"] is None
    assert payload["risk_aging"]["blockers"]["count"] == 0
    assert payload["risk_aging"]["high_severity_bugs"]["count"] == 0
    assert payload["last_24_hours"]["has_baseline"] is False
    assert payload["reasons"] == ["No major risk indicators"]
    assert payload["reason_details"] == []
    assert payload["thresholds"]["median_cycle_time_days_yellow"] == 7.0


def test_not_computed_cycle_time_passes_readiness_gate_but_not_confidence(
    client: TestClient,
) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(
            session,
            "LHPM-1",
            "REL-1",
            "Done",
            is_blocker=False,
            issue_type="Story",
            priority="Medium",
        )

    assert client.post("/releases/REL-1/recompute").status_code == 200
    signal = client.get("/releases/REL-1/signal").json()
    metrics = client.get("/releases/REL-1/metrics").json()

    assert signal["signal"] == "INCONCLUSIVE"
    assert signal["confidence_score"] is None
    assert len(signal["release_gates"]) == 5
    cycle_gate = next(
        gate
        for gate in signal["release_gates"]
        if gate["metric_name"] == "median_cycle_time_days"
    )
    assert cycle_gate["passed"] is True
    assert cycle_gate["value"] is None
    assert metrics["metric_availability"]["metrics"]["confidence_score"]["available"] is False
    assert metrics["metric_availability"]["metrics"]["gates_passed_count"]["available"] is True
    assert metrics["metric_availability"]["metrics"]["readiness_pct"]["available"] is True
    assert metrics["calculation_provenance"]["component_outputs"]["readiness_pct"] == 100.0


def test_partial_cycle_time_does_not_pass_readiness_gate(client: TestClient) -> None:
    base = datetime(2026, 7, 1, tzinfo=UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(
            session,
            "LHPM-1",
            "REL-1",
            "Done",
            is_blocker=False,
            issue_type="Story",
            priority="Medium",
        )
        issue = session.scalar(select(Issue).where(Issue.issue_key == "LHPM-1"))
        assert issue is not None
        issue.jira_changelog_complete = False
        session.add_all(
            [
                IssueHistory(
                    issue_key="LHPM-1",
                    field_name="status",
                    old_value="To Do",
                    new_value="In Progress",
                    changed_at=base,
                ),
                IssueHistory(
                    issue_key="LHPM-1",
                    field_name="status",
                    old_value="In Progress",
                    new_value="Done",
                    changed_at=base + timedelta(days=2),
                ),
            ]
        )
        session.commit()

    assert client.post("/releases/REL-1/recompute").status_code == 200
    signal = client.get("/releases/REL-1/signal").json()
    metrics = client.get("/releases/REL-1/metrics").json()

    assert signal["signal"] == "INCONCLUSIVE"
    assert all(
        gate["metric_name"] != "median_cycle_time_days"
        for gate in signal["release_gates"]
    )
    cycle_availability = metrics["metric_availability"]["metrics"][
        "median_cycle_time_days"
    ]
    assert cycle_availability["status"] == "PARTIAL"
    assert cycle_availability["missing_issue_keys"] == ["LHPM-1"]


def test_get_release_signal_returns_risk_aging_from_latest_snapshot(client: TestClient) -> None:
    snapshot_at = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(
            session,
            issue_key="LHPM-1",
            release_id="REL-1",
            status="In Progress",
            is_blocker=True,
            created_at=snapshot_at - timedelta(days=14),
            issue_type="Story",
            priority="Medium",
        )
        _seed_issue(
            session,
            issue_key="LHPM-2",
            release_id="REL-1",
            status="To Do",
            is_blocker=True,
            created_at=snapshot_at - timedelta(days=7),
            issue_type="Story",
            priority="Medium",
        )
        _seed_issue(
            session,
            issue_key="LHPM-3",
            release_id="REL-1",
            status="In Progress",
            is_blocker=False,
            created_at=snapshot_at - timedelta(days=8),
            issue_type="Bug",
            priority="High",
        )
        _seed_issue(
            session,
            issue_key="LHPM-4",
            release_id="REL-1",
            status="In Progress",
            is_blocker=False,
            created_at=snapshot_at - timedelta(days=9),
            issue_type="Bug",
            priority="Critical",
        )
        _seed_issue(
            session,
            issue_key="LHPM-5",
            release_id="REL-1",
            status="To Do",
            is_blocker=False,
            created_at=snapshot_at - timedelta(days=10),
            issue_type="Bug",
            priority="Highest",
        )
        _seed_issue(
            session,
            issue_key="LHPM-6",
            release_id="REL-1",
            status="Done",
            is_blocker=True,
            created_at=snapshot_at - timedelta(days=30),
            issue_type="Bug",
            priority="High",
        )
        _seed_snapshot(
            session,
            release_id="REL-1",
            snapshot_at=snapshot_at,
            open_blockers=2,
            open_high_severity_bugs=3,
            open_blocker_issue_keys=["LHPM-1", "LHPM-2"],
            open_high_severity_bug_issue_keys=["LHPM-3", "LHPM-4", "LHPM-5"],
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        _seed_signal(session, release_id="REL-1", signal="RED")

    response = client.get("/releases/REL-1/signal")
    assert response.status_code == 200
    risk_aging = response.json()["risk_aging"]
    assert risk_aging["as_of"] == "2026-01-20T12:00:00Z"
    blocker_tickets = risk_aging["blockers"].pop("tickets")
    assert risk_aging["blockers"] == {
        "count": 2,
        "known_count": 2,
        "unknown_count": 0,
        "oldest_age_days": 14.0,
        "average_age_days": 10.5,
    }
    assert blocker_tickets[0] == {
        "key": "LHPM-1",
        "age_days": 14.0,
        "issue_age_days": 14.0,
        "jira_created_at": "2026-01-06T12:00:00Z",
        "risk_started_at": "2026-01-06T12:00:00Z",
        "risk_start_source_field": "jira_created_at",
        "risk_start_source_changed_at": "2026-01-06T12:00:00Z",
        "history_complete": True,
        "explanation": None,
    }
    high_bug_tickets = risk_aging["high_severity_bugs"].pop("tickets")
    assert risk_aging["high_severity_bugs"] == {
        "count": 3,
        "known_count": 3,
        "unknown_count": 0,
        "oldest_age_days": 10.0,
        "average_age_days": 9.0,
    }
    assert [ticket["key"] for ticket in high_bug_tickets] == ["LHPM-3", "LHPM-4", "LHPM-5"]
    assert [ticket["issue_age_days"] for ticket in high_bug_tickets] == [8.0, 9.0, 10.0]
    assert all(ticket["history_complete"] is True for ticket in high_bug_tickets)


def test_get_release_signal_risk_aging_honors_zero_count_snapshot(client: TestClient) -> None:
    snapshot_at = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(
            session,
            issue_key="LHPM-1",
            release_id="REL-1",
            status="In Progress",
            is_blocker=True,
            created_at=snapshot_at - timedelta(days=14),
        )
        _seed_snapshot(
            session,
            release_id="REL-1",
            snapshot_at=snapshot_at,
            open_blockers=0,
            open_high_severity_bugs=0,
            open_blocker_issue_keys=[],
            open_high_severity_bug_issue_keys=[],
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        _seed_signal(session, release_id="REL-1", signal="GREEN")

    response = client.get("/releases/REL-1/signal")
    assert response.status_code == 200
    risk_aging = response.json()["risk_aging"]
    assert risk_aging["blockers"] == {
        "count": 0,
        "known_count": 0,
        "unknown_count": 0,
        "oldest_age_days": None,
        "average_age_days": None,
        "tickets": [],
    }
    assert risk_aging["high_severity_bugs"] == {
        "count": 0,
        "known_count": 0,
        "unknown_count": 0,
        "oldest_age_days": None,
        "average_age_days": None,
        "tickets": [],
    }


def test_get_release_signal_risk_age_resets_when_risk_reactivates(client: TestClient) -> None:
    snapshot_at = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(
            session,
            issue_key="LHPM-1",
            release_id="REL-1",
            status="In Progress",
            is_blocker=False,
            created_at=snapshot_at - timedelta(days=20),
            issue_type="Bug",
            priority="High",
        )
        session.add_all(
            [
                IssueHistory(
                    issue_key="LHPM-1",
                    field_name="status",
                    old_value="In Progress",
                    new_value="Done",
                    changed_at=snapshot_at - timedelta(days=5),
                ),
                IssueHistory(
                    issue_key="LHPM-1",
                    field_name="status",
                    old_value="Done",
                    new_value="In Progress",
                    changed_at=snapshot_at - timedelta(days=2),
                ),
            ]
        )
        _seed_snapshot(
            session,
            release_id="REL-1",
            snapshot_at=snapshot_at,
            open_blockers=0,
            open_high_severity_bugs=1,
            open_high_severity_bug_issue_keys=["LHPM-1"],
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        _seed_signal(session, release_id="REL-1", signal="YELLOW")

    response = client.get("/releases/REL-1/signal")

    assert response.status_code == 200
    risk_group = response.json()["risk_aging"]["high_severity_bugs"]
    ticket = risk_group.pop("tickets")[0]
    assert risk_group == {
        "count": 1,
        "known_count": 1,
        "unknown_count": 0,
        "oldest_age_days": 2.0,
        "average_age_days": 2.0,
    }
    assert ticket == {
        "key": "LHPM-1",
        "age_days": 2.0,
        "issue_age_days": 20.0,
        "jira_created_at": "2025-12-31T12:00:00Z",
        "risk_started_at": "2026-01-18T12:00:00Z",
        "risk_start_source_field": "status",
        "risk_start_source_changed_at": "2026-01-18T12:00:00Z",
        "history_complete": True,
        "explanation": None,
    }


def test_get_release_signal_marks_risk_age_unknown_without_complete_history(client: TestClient) -> None:
    snapshot_at = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(
            session,
            issue_key="LHPM-1",
            release_id="REL-1",
            status="In Progress",
            is_blocker=True,
            created_at=snapshot_at - timedelta(days=20),
        )
        issue = session.scalar(select(Issue).where(Issue.issue_key == "LHPM-1"))
        assert issue is not None
        issue.jira_changelog_complete = False
        _seed_snapshot(
            session,
            release_id="REL-1",
            snapshot_at=snapshot_at,
            open_blockers=1,
            open_high_severity_bugs=0,
            open_blocker_issue_keys=["LHPM-1"],
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        _seed_signal(session, release_id="REL-1", signal="RED")

    response = client.get("/releases/REL-1/signal")

    assert response.status_code == 200
    risk_group = response.json()["risk_aging"]["blockers"]
    ticket = risk_group.pop("tickets")[0]
    assert risk_group == {
        "count": 1,
        "known_count": 0,
        "unknown_count": 1,
        "oldest_age_days": None,
        "average_age_days": None,
    }
    assert ticket == {
        "key": "LHPM-1",
        "age_days": None,
        "issue_age_days": 20.0,
        "jira_created_at": "2025-12-31T12:00:00Z",
        "risk_started_at": None,
        "risk_start_source_field": None,
        "risk_start_source_changed_at": None,
        "history_complete": False,
        "explanation": "Risk start unavailable from Jira history.",
    }


def test_get_release_signal_returns_last_24_hours_deltas(client: TestClient) -> None:
    latest_at = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)
    baseline_at = latest_at - timedelta(hours=25)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1", release_date=latest_at + timedelta(days=5))
        _seed_issue(session, "LHPM-1", "REL-1", "Done", is_blocker=False, issue_type="Story", priority="Medium")
        _seed_snapshot(
            session,
            release_id="REL-1",
            snapshot_at=baseline_at,
            open_blockers=3,
            open_high_severity_bugs=3,
            completed_tickets=2,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=11.0,
            median_cycle_time_days=2.0,
        )
        _seed_snapshot(
            session,
            release_id="REL-1",
            snapshot_at=latest_at - timedelta(hours=23),
            open_blockers=99,
            open_high_severity_bugs=99,
            completed_tickets=99,
            scope_churn_7d_pct=99.0,
            reopen_rate_pct=99.0,
            median_cycle_time_days=99.0,
        )
        _seed_snapshot(
            session,
            release_id="REL-1",
            snapshot_at=latest_at,
            open_blockers=5,
            open_high_severity_bugs=2,
            completed_tickets=6,
            scope_churn_7d_pct=0.0,
            reopen_rate_pct=0.0,
            median_cycle_time_days=2.0,
        )
        _seed_signal(session, release_id="REL-1", signal="RED")

    response = client.get("/releases/REL-1/signal")
    assert response.status_code == 200
    last_24_hours = response.json()["last_24_hours"]
    assert last_24_hours["as_of"] == "2026-01-20T12:00:00Z"
    assert last_24_hours["baseline_at"] == "2026-01-19T11:00:00Z"
    assert last_24_hours["has_baseline"] is True
    assert last_24_hours["items"] == [
        {
            "metric_name": "open_blockers",
            "label": "blocker",
            "delta": 2.0,
            "value_type": "count",
            "impact": "negative",
        },
        {
            "metric_name": "open_high_severity_bugs",
            "label": "high severity bug",
            "delta": -1.0,
            "value_type": "count",
            "impact": "positive",
        },
        {
            "metric_name": "completed_tickets",
            "label": "completed ticket",
            "delta": 4.0,
            "value_type": "count",
            "impact": "positive",
        },
        {
            "metric_name": "confidence_score",
            "label": "Confidence",
            "delta": 3.0,
            "value_type": "percentage",
            "impact": "positive",
        },
    ]
    outlook = response.json()["release_outlook"]
    assert outlook["label"] == "AT RISK"
    assert outlook["signal"] == "RED"
    assert outlook["snapshot_at"] == "2026-01-20T12:00:00Z"
    assert outlook["release_date"] == "2026-01-25T12:00:00Z"
    assert outlook["days_remaining"] == 5
    assert outlook["confidence_change_24h"] == 3.0
    assert outlook["confidence_baseline_at"] == "2026-01-19T11:00:00Z"
    assert outlook["passed_gate_count"] == 3
    assert outlook["failed_gate_count"] == 2
    assert {item["metric_name"] for item in outlook["active_conditions"]} == {
        "open_blockers",
        "open_high_severity_bugs",
    }
    assert outlook["disclaimer"] == "This outlook reflects the latest stored snapshot and is not a forecast."
