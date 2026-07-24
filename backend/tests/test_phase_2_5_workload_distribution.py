from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Issue, IssueSprint, Sprint
from app.services.analytics_service import AnalyticsService
from app.services.recommendation_engine import RecommendationEngine


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, class_=Session)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def _sprint() -> Sprint:
    now = datetime.now(UTC)
    return Sprint(
        sprint_id="10",
        name="Sprint 10",
        state="active",
        project_key="LHPM",
        board_id="1",
        start_date=now - timedelta(days=7),
        end_date=now + timedelta(days=7),
        complete_date=None,
        goal=None,
    )


def _issue(
    key: str,
    points: float | None,
    *,
    status: str | None = "To Do",
    assignee: str | None = "Ava",
    assignee_id: str | None = "jira-ava",
) -> Issue:
    return Issue(
        issue_key=key,
        summary=f"{key} summary",
        issue_type="Story",
        status=status,
        priority="Medium",
        assignee=assignee,
        jira_assignee_id=assignee_id,
        story_points=points,
        release_id=None,
        is_blocker=False,
        jira_blocker_flag=False,
        jira_changelog_complete=True,
    )


def _add_scope(session: Session, issues: list[Issue]) -> None:
    session.add(_sprint())
    session.add_all(issues)
    session.add_all(
        IssueSprint(issue_key=issue.issue_key, sprint_id="10") for issue in issues
    )
    session.flush()


@pytest.mark.parametrize(
    ("top_points", "other_points", "expected_pct", "expected_band"),
    [
        (3499, 6501, 65.01, "critical"),
        (50, 50, 50.0, "watch"),
        (51, 49, 51.0, "critical"),
    ],
)
def test_workload_distribution_threshold_boundaries(
    db_session: Session,
    top_points: float,
    other_points: float,
    expected_pct: float,
    expected_band: str,
) -> None:
    # Two buckets make the larger share authoritative; 34.99% cannot be the top
    # share with only two buckets, so the first case verifies precise rounding.
    _add_scope(
        db_session,
        [
            _issue("LHPM-1", top_points, assignee="Ava", assignee_id="jira-ava"),
            _issue("LHPM-2", other_points, assignee="Noah", assignee_id="jira-noah"),
        ],
    )

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.workload_concentration_pct == expected_pct
    assert snapshot.workload_distribution_status == "COMPUTED"
    assert snapshot.workload_distribution_evidence["calculation_status"] == "COMPUTED"
    assert snapshot.workload_distribution_evidence["workload_concentration_pct"] == expected_pct
    assert snapshot.workload_distribution_evidence["risk_band"] == expected_band


def test_workload_distribution_healthy_boundary_below_35(db_session: Session) -> None:
    _add_scope(
        db_session,
        [
            _issue("LHPM-1", 34.99, assignee="Ava", assignee_id="jira-ava"),
            _issue("LHPM-2", 33.01, assignee="Noah", assignee_id="jira-noah"),
            _issue("LHPM-3", 32.0, assignee="Mira", assignee_id="jira-mira"),
        ],
    )

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.workload_concentration_pct == 34.99
    assert snapshot.workload_distribution_evidence["risk_band"] == "healthy"
    assert all(
        item.title != "Reduce workload concentration"
        for item in RecommendationEngine.build_sprint_recommendations(snapshot)
    )


def test_workload_distribution_watch_boundary_at_35(db_session: Session) -> None:
    _add_scope(
        db_session,
        [
            _issue("LHPM-1", 35, assignee="Ava", assignee_id="jira-ava"),
            _issue("LHPM-2", 33, assignee="Noah", assignee_id="jira-noah"),
            _issue("LHPM-3", 32, assignee="Mira", assignee_id="jira-mira"),
        ],
    )

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.workload_concentration_pct == 35.0
    assert snapshot.workload_distribution_evidence["risk_band"] == "watch"
    assert any(
        item.title == "Reduce workload concentration"
        for item in RecommendationEngine.build_sprint_recommendations(snapshot)
    )


def test_workload_distribution_partial_coverage_returns_evidence_and_recommendation(
    db_session: Session,
) -> None:
    _add_scope(
        db_session,
        [
            _issue("LHPM-1", 6, assignee="Ava", assignee_id="jira-ava"),
            _issue("LHPM-2", None, assignee="Noah", assignee_id="jira-noah"),
        ],
    )

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.workload_distribution_status == "PARTIAL"
    assert snapshot.workload_concentration_pct == 100.0
    assert snapshot.workload_distribution_evidence["excluded_active_issue_keys"] == [
        "LHPM-2"
    ]
    assert snapshot.workload_distribution_evidence["calculation_status"] == "PARTIAL"
    assert snapshot.workload_distribution_evidence["workload_concentration_pct"] == 100.0
    availability = snapshot.calculation_provenance["availability"]["metrics"][
        "workload_concentration_pct"
    ]
    assert availability["status"] == "PARTIAL"
    assert availability["available"] is True
    assert availability["missing_issue_keys"] == ["LHPM-2"]
    recommendations = RecommendationEngine.build_sprint_recommendations(snapshot)
    workload_recommendation = next(
        item for item in recommendations if item.title == "Reduce workload concentration"
    )
    assert workload_recommendation.dataStatus == "PARTIAL"
    assert workload_recommendation.explanations == snapshot.workload_distribution_explanations


def test_workload_distribution_below_half_coverage_is_inconclusive(
    db_session: Session,
) -> None:
    _add_scope(
        db_session,
        [
            _issue("LHPM-1", 3),
            _issue("LHPM-2", None),
            _issue("LHPM-3", None),
        ],
    )

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.workload_distribution_status == "INCONCLUSIVE"
    assert snapshot.workload_concentration_pct is None
    assert all(
        item.title != "Reduce workload concentration"
        for item in RecommendationEngine.build_sprint_recommendations(snapshot)
    )


def test_workload_distribution_missing_status_is_inconclusive_and_sorted(
    db_session: Session,
) -> None:
    _add_scope(
        db_session,
        [
            _issue("LHPM-2", 3, status=None),
            _issue("LHPM-1", 3, status="To Do"),
        ],
    )

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.workload_distribution_status == "INCONCLUSIVE"
    assert snapshot.workload_concentration_pct is None
    assert snapshot.workload_distribution_evidence["missing_status_issue_keys"] == [
        "LHPM-2"
    ]


def test_workload_distribution_normalizes_fallback_identity_and_breaks_ties(
    db_session: Session,
) -> None:
    _add_scope(
        db_session,
        [
            _issue("LHPM-2", 2, assignee="ava", assignee_id=None),
            _issue("LHPM-1", 3, assignee=" Ava ", assignee_id=None),
            _issue("LHPM-3", 5, assignee="Noah", assignee_id="jira-noah"),
        ],
    )

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.workload_distribution_status == "PARTIAL"
    assert snapshot.workload_concentration_pct == 50.0
    evidence = snapshot.workload_distribution_evidence
    assert evidence["assignee_identity_fallback_issue_keys"] == ["LHPM-1", "LHPM-2"]
    assert evidence["top_assignee"]["assignee_key"] == "display:ava"
    assert evidence["top_assignee"]["assignee"] == "Ava"


def test_workload_distribution_uses_explicit_unassigned_bucket(db_session: Session) -> None:
    _add_scope(
        db_session,
        [
            _issue("LHPM-1", 6, assignee=None, assignee_id=None),
            _issue("LHPM-2", 4, assignee="Noah", assignee_id="jira-noah"),
        ],
    )

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.workload_distribution_status == "COMPUTED"
    assert snapshot.workload_distribution_evidence["top_assignee"] == {
        "assignee_key": "unassigned",
        "assignee": "Unassigned",
        "story_points": 6.0,
        "issue_keys": ["LHPM-1"],
    }


def test_workload_distribution_no_active_work_is_not_applicable(db_session: Session) -> None:
    _add_scope(db_session, [_issue("LHPM-1", 3, status="Done")])

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.workload_distribution_status == "NOT_APPLICABLE"
    assert snapshot.workload_concentration_pct is None


def test_workload_distribution_zero_point_denominator_is_not_computed(
    db_session: Session,
) -> None:
    _add_scope(db_session, [_issue("LHPM-1", 0), _issue("LHPM-2", 0)])

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.workload_distribution_status == "NOT_COMPUTED"
    assert snapshot.workload_concentration_pct is None
    assert snapshot.workload_distribution_evidence["total_active_points"] == 0.0
