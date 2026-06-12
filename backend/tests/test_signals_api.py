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
from app.models import Issue, MetricSnapshot, Release, ReleaseSignal


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
    snapshot_at: datetime | None = None,
    open_blocker_issue_keys: list[str] | None = None,
    open_high_severity_bug_issue_keys: list[str] | None = None,
    completed_tickets: int | None = None,
) -> None:
    session.add(
        MetricSnapshot(
            release_id=release_id,
            snapshot_at=snapshot_at or datetime.now(UTC),
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
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()


def _seed_signal(session: Session, release_id: str, signal: str) -> None:
    now = datetime.now(UTC)
    session.add(
        ReleaseSignal(
            release_id=release_id,
            signal=signal,
            reasons=["Seeded signal"],
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
        "status_label": "NOT COMPUTED",
        "confidence_score": None,
        "confidence_breakdown": None,
        "summary": "Signal has not been computed yet for this release snapshot.",
        "reasons": [],
        "reason_details": [],
        "release_gates": [],
        "critical_risks": [],
        "warnings": [],
        "primary_risk": None,
        "risk_aging": {
            "blockers": {"count": 0, "oldest_age_days": None, "average_age_days": None, "tickets": []},
            "high_severity_bugs": {"count": 0, "oldest_age_days": None, "average_age_days": None, "tickets": []},
            "as_of": None,
        },
        "last_24_hours": {"as_of": None, "baseline_at": None, "has_baseline": False, "items": []},
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
            "updated_at": None,
        }


def test_get_release_signal_after_metrics_recompute_uses_confidence_band(client: TestClient) -> None:
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
        _seed_issue(session, issue_key="LHPM-1", release_id="REL-1", status="In Progress", is_blocker=True)

    recompute = client.post("/releases/REL-1/recompute")
    assert recompute.status_code == 200

    response = client.get("/releases/REL-1/signal")
    assert response.status_code == 200
    payload = response.json()
    assert payload["release_id"] == "REL-1"
    assert payload["signal"] == "YELLOW"
    assert payload["status_label"] == "RELEASE NEEDS ATTENTION"
    assert payload["confidence_score"] == 72.0
    assert payload["confidence_breakdown"]["totalScore"] == 72.0
    assert [component["name"] for component in payload["confidence_breakdown"]["components"]] == [
        "Delivery",
        "Quality",
        "Flow",
        "Risk",
    ]
    assert any(gate["metric_name"] == "open_blockers" and not gate["passed"] for gate in payload["release_gates"])
    assert any(risk["metric_name"] == "open_blockers" for risk in payload["critical_risks"])
    assert payload["risk_aging"]["blockers"]["count"] == 1
    assert any("blocker" in reason.lower() for reason in payload["reasons"])
    assert payload["thresholds"]["open_blockers_red"] == 0
    assert payload["thresholds"]["confidence_score_yellow_max"] == 90.0
    assert any(detail["metric_name"] == "open_blockers" for detail in payload["reason_details"])
    assert all(detail["message"] in payload["reasons"] for detail in payload["reason_details"])


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
    assert payload["status_label"] == "READY FOR RELEASE"
    assert payload["confidence_score"] == 100.0
    assert payload["confidence_breakdown"]["totalScore"] == 100.0
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
    assert risk_aging["blockers"] == {
        "count": 2,
        "oldest_age_days": 14.0,
        "average_age_days": 10.5,
        "tickets": [{"key": "LHPM-1", "age_days": 14.0}, {"key": "LHPM-2", "age_days": 7.0}],
    }
    assert risk_aging["high_severity_bugs"] == {
        "count": 3,
        "oldest_age_days": 10.0,
        "average_age_days": 9.0,
        "tickets": [
            {"key": "LHPM-3", "age_days": 8.0},
            {"key": "LHPM-4", "age_days": 9.0},
            {"key": "LHPM-5", "age_days": 10.0},
        ],
    }


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
        "oldest_age_days": None,
        "average_age_days": None,
        "tickets": [],
    }
    assert risk_aging["high_severity_bugs"] == {
        "count": 0,
        "oldest_age_days": None,
        "average_age_days": None,
        "tickets": [],
    }


def test_get_release_signal_returns_last_24_hours_deltas(client: TestClient) -> None:
    latest_at = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)
    baseline_at = latest_at - timedelta(hours=25)
    with app.state.testing_session_local() as session:
        _seed_release(session, release_id="REL-1")
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
