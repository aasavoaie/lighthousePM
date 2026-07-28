from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.db.base import Base
from app.models import Issue, IssueHistory, IssueSprint, Sprint
from app.services.analytics_service import AnalyticsService


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, class_=Session)
    with testing_session() as session:
        yield session


def _sprint(now: datetime) -> Sprint:
    return Sprint(
        sprint_id="10",
        name="Sprint 10",
        state="active",
        project_key="LHPM",
        start_date=now - timedelta(days=2),
        end_date=now + timedelta(days=2),
    )


def _issue(
    key: str,
    *,
    story_points: float | None = 1,
    history_complete: bool = True,
) -> Issue:
    return Issue(
        issue_key=key,
        summary=key,
        issue_type="Story",
        status="To Do",
        priority="Medium",
        story_points=story_points,
        jira_blocker_flag=False,
        jira_changelog_complete=history_complete,
    )


def _history(
    key: str,
    old_value: str | None,
    new_value: str | None,
    changed_at: datetime,
    *,
    field_name: str = "sprint",
) -> IssueHistory:
    return IssueHistory(
        issue_key=key,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        changed_at=changed_at,
    )


def test_scope_creep_is_authoritative_and_independent_of_story_points(
    db_session: Session,
) -> None:
    now = datetime.now(UTC)
    db_session.add(_sprint(now))
    db_session.add_all(
        [
            _issue("LHPM-1", story_points=1),
            _issue("LHPM-2", story_points=None),
            _issue("LHPM-3", story_points=None),
            _issue("LHPM-4", story_points=None),
        ]
    )
    db_session.add_all(
        [
            IssueSprint(issue_key="LHPM-1", sprint_id="10"),
            IssueSprint(issue_key="LHPM-2", sprint_id="10"),
            IssueSprint(issue_key="LHPM-3", sprint_id="10"),
        ]
    )
    db_session.flush()
    db_session.add_all(
        [
            _history("LHPM-3", "Sprint 9", "Sprint 10", now - timedelta(days=1)),
            _history("LHPM-4", "Sprint 10", "Sprint 11", now - timedelta(hours=1)),
        ]
    )
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.delivery_confidence_status == "INCONCLUSIVE"
    assert snapshot.scope_creep_status == "COMPUTED"
    assert snapshot.scope_creep_pct == 66.67
    assert snapshot.scope_creep_evidence["initial_commitment_count"] == 3
    assert snapshot.scope_creep_evidence["scope_added_issue_keys"] == ["LHPM-3"]
    assert snapshot.scope_creep_evidence["scope_removed_issue_keys"] == ["LHPM-4"]
    availability = snapshot.calculation_provenance["availability"]["metrics"][
        "scope_creep_pct"
    ]
    assert availability["status"] == "COMPUTED"
    assert availability["available"] is True


def test_scope_creep_uses_exact_sprint_identity(db_session: Session) -> None:
    now = datetime.now(UTC)
    db_session.add(_sprint(now))
    db_session.add_all([_issue("LHPM-1"), _issue("LHPM-2")])
    db_session.add_all(
        [
            IssueSprint(issue_key="LHPM-1", sprint_id="10"),
            IssueSprint(issue_key="LHPM-2", sprint_id="10"),
        ]
    )
    db_session.flush()
    db_session.add_all(
        [
            _history("LHPM-1", "Sprint 9", "Sprint 110", now - timedelta(hours=3)),
            _history(
                "LHPM-2",
                "id=9,name=Sprint 9",
                "id=10,name=Sprint 10",
                now - timedelta(hours=2),
            ),
        ]
    )
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.scope_creep_pct == 100.0
    assert snapshot.scope_creep_evidence["scope_added_issue_keys"] == ["LHPM-2"]


def test_scope_creep_accepts_configured_jira_sprint_field_id(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    issue_keys = [f"LHPM-{index:02d}" for index in range(1, 22)]
    db_session.add(_sprint(now))
    db_session.add_all([_issue(issue_key) for issue_key in issue_keys])
    db_session.add_all(
        [IssueSprint(issue_key=issue_key, sprint_id="10") for issue_key in issue_keys]
    )
    db_session.flush()
    db_session.add_all(
        [
            _history(
                issue_key,
                "",
                "Sprint 10",
                now - timedelta(hours=1),
                field_name="customfield_10020",
            )
            for issue_key in ("LHPM-20", "LHPM-21")
        ]
    )
    db_session.flush()
    monkeypatch.setenv("JIRA_FIELD_SPRINT", "customfield_10020")
    get_settings.cache_clear()

    try:
        snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")
    finally:
        get_settings.cache_clear()

    assert snapshot.scope_creep_pct == 10.53
    assert snapshot.scope_creep_evidence["initial_commitment_count"] == 19
    assert snapshot.scope_creep_evidence["scope_added_issue_keys"] == [
        "LHPM-20",
        "LHPM-21",
    ]
    assert snapshot.scope_creep_evidence["sprint_changelog_fields"] == [
        "customfield_10020",
        "sprint",
    ]


def test_scope_creep_counts_readdition_as_another_event(
    db_session: Session,
) -> None:
    now = datetime.now(UTC)
    issue_keys = [f"LHPM-{index:02d}" for index in range(1, 23)]
    current_scope_issue_keys = [f"LHPM-{index:02d}" for index in range(1, 19)]
    db_session.add(_sprint(now))
    db_session.add_all([_issue(issue_key) for issue_key in issue_keys])
    db_session.add_all(
        [
            IssueSprint(issue_key=issue_key, sprint_id="10")
            for issue_key in current_scope_issue_keys
        ]
    )
    db_session.flush()
    db_session.add_all(
        [
            *[
                _history(
                    issue_key,
                    "",
                    "Sprint 10",
                    now - timedelta(hours=6),
                )
                for issue_key in (
                    "LHPM-17",
                    "LHPM-18",
                    "LHPM-19",
                    "LHPM-20",
                    "LHPM-21",
                )
            ],
            *[
                _history(
                    issue_key,
                    "Sprint 10",
                    "",
                    now - timedelta(hours=4),
                )
                for issue_key in (
                    "LHPM-17",
                    "LHPM-18",
                    "LHPM-19",
                    "LHPM-20",
                    "LHPM-21",
                    "LHPM-22",
                )
            ],
            _history("LHPM-17", "", "Sprint 10", now - timedelta(hours=2)),
            _history("LHPM-18", "", "Sprint 10", now - timedelta(hours=2)),
        ]
    )
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    evidence = snapshot.scope_creep_evidence
    assert snapshot.ruleset_version == 5
    assert snapshot.scope_creep_pct == 76.47
    assert evidence["initial_commitment_count"] == 17
    assert evidence["scope_added_count"] == 7
    assert evidence["scope_removed_count"] == 6
    assert len(evidence["scope_addition_events"]) == 7
    assert len(evidence["scope_removal_events"]) == 6
    assert evidence["scope_added_issue_keys"] == [
        "LHPM-17",
        "LHPM-18",
        "LHPM-19",
        "LHPM-20",
        "LHPM-21",
    ]
    assert evidence["scope_removed_issue_keys"] == [
        "LHPM-17",
        "LHPM-18",
        "LHPM-19",
        "LHPM-20",
        "LHPM-21",
        "LHPM-22",
    ]


def test_zero_initial_commitment_never_becomes_healthy_stability(
    db_session: Session,
) -> None:
    now = datetime.now(UTC)
    db_session.add(_sprint(now))
    db_session.add(_issue("LHPM-1"))
    db_session.add(IssueSprint(issue_key="LHPM-1", sprint_id="10"))
    db_session.flush()
    db_session.add(
        _history("LHPM-1", "Sprint 9", "Sprint 10", now - timedelta(hours=1))
    )
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.scope_creep_pct is None
    assert snapshot.scope_creep_status == "NOT_COMPUTED"
    assert snapshot.scope_creep_evidence["initial_commitment_count"] == 0
    assert snapshot.delivery_confidence_status == "INCONCLUSIVE"
    assert snapshot.delivery_confidence_score is None
    assert any(
        "reconstructed initial commitment is zero" in explanation
        for explanation in snapshot.delivery_confidence_explanations
    )


def test_incomplete_project_history_returns_partial_confirmed_evidence(
    db_session: Session,
) -> None:
    now = datetime.now(UTC)
    db_session.add(_sprint(now))
    db_session.add_all(
        [
            _issue("LHPM-1"),
            _issue("LHPM-2", history_complete=False),
        ]
    )
    db_session.add(IssueSprint(issue_key="LHPM-1", sprint_id="10"))
    db_session.flush()

    snapshot = AnalyticsService().recompute_sprint_metrics(db_session, "10")

    assert snapshot.scope_creep_pct is None
    assert snapshot.scope_creep_status == "PARTIAL"
    assert snapshot.scope_creep_evidence["incomplete_history_issue_keys"] == [
        "LHPM-2"
    ]
    availability = snapshot.calculation_provenance["availability"]["metrics"][
        "scope_creep_pct"
    ]
    assert availability["status"] == "PARTIAL"
    assert availability["missing_issue_keys"] == ["LHPM-2"]
