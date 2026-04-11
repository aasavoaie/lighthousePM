"""Tests for AnalyticsService — uses in-memory SQLite via StaticPool."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base
from app.models import Issue, IssueHistory, MetricSnapshot, Release
from app.services.analytics_service import AnalyticsService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_engine() -> object:
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture()
def db_session() -> Session:
    engine = _make_engine()
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    session = TestingSession()
    yield session
    session.close()


def _release(release_id: str = "R1", name: str = "v1.0") -> Release:
    return Release(
        release_id=release_id,
        name=name,
        project_key="PROJ",
        status="unreleased",
    )


def _issue(
    key: str,
    status: str,
    issue_type: str = "Story",
    priority: str = "Medium",
    release_id: str = "R1",
    is_blocker: bool = False,
) -> Issue:
    return Issue(
        issue_key=key,
        summary=key,
        issue_type=issue_type,
        status=status,
        priority=priority,
        release_id=release_id,
        is_blocker=is_blocker,
    )


def _history(
    issue_key: str,
    field_name: str,
    old_value: str | None,
    new_value: str | None,
    changed_at: datetime,
) -> IssueHistory:
    return IssueHistory(
        issue_key=issue_key,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        changed_at=changed_at,
    )


# ---------------------------------------------------------------------------
# open_blockers
# ---------------------------------------------------------------------------


def test_open_blockers_counts_only_open(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "In Progress", is_blocker=True))
    db_session.add(_issue("P-2", "To Do", is_blocker=True))
    db_session.add(_issue("P-3", "Done", is_blocker=True))  # closed — excluded
    db_session.add(_issue("P-4", "In Progress", is_blocker=False))  # not a blocker
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.open_blockers == 2


def test_open_blockers_empty_release(db_session: Session) -> None:
    db_session.add(_release())
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.open_blockers == 0


# ---------------------------------------------------------------------------
# open_high_severity_bugs
# ---------------------------------------------------------------------------


def test_open_high_severity_bugs_counts_correctly(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "In Progress", issue_type="Bug", priority="High"))
    db_session.add(_issue("P-2", "To Do", issue_type="Bug", priority="Critical"))
    db_session.add(_issue("P-3", "Done", issue_type="Bug", priority="High"))  # done — excluded
    db_session.add(_issue("P-4", "In Progress", issue_type="Bug", priority="Medium"))  # not high
    db_session.add(_issue("P-5", "In Progress", issue_type="Story", priority="High"))  # not a bug
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.open_high_severity_bugs == 2


def test_open_high_severity_bugs_case_insensitive(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "in progress", issue_type="BUG", priority="HIGHEST"))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.open_high_severity_bugs == 1


# ---------------------------------------------------------------------------
# scope_completed_pct
# ---------------------------------------------------------------------------


def test_scope_completed_pct_empty_release(db_session: Session) -> None:
    db_session.add(_release())
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.scope_completed_pct == 0.0


def test_scope_completed_pct_partial(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "Done"))
    db_session.add(_issue("P-2", "Closed"))
    db_session.add(_issue("P-3", "In Progress"))
    db_session.add(_issue("P-4", "To Do"))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.scope_completed_pct == 50.0


def test_scope_completed_pct_all_done(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "Done"))
    db_session.add(_issue("P-2", "Resolved"))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.scope_completed_pct == 100.0


# ---------------------------------------------------------------------------
# scope_churn_7d_pct
# ---------------------------------------------------------------------------


def test_scope_churn_7d_counts_recent_fix_version_changes(db_session: Session) -> None:
    db_session.add(_release(name="v1.0"))
    db_session.add(_issue("P-1", "In Progress"))
    db_session.add(_issue("P-2", "To Do"))
    db_session.flush()

    now = datetime.now(UTC)
    # P-1 was re-assigned to v1.0 (new_value matches) 3 days ago — counts as churn
    db_session.add(_history("P-1", "fix version", "v0.9", "v1.0", now - timedelta(days=3)))
    # P-2 was removed from v1.0 (old_value matches) 5 days ago — also churn
    db_session.add(_history("P-2", "fix version", "v1.0", "v2.0", now - timedelta(days=5)))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.scope_churn_7d_pct == 100.0  # 2 churned / 2 total


def test_scope_churn_7d_excludes_old_changes(db_session: Session) -> None:
    db_session.add(_release(name="v1.0"))
    db_session.add(_issue("P-1", "Done"))
    db_session.flush()

    now = datetime.now(UTC)
    # Change was 10 days ago — outside the 7-day window
    db_session.add(_history("P-1", "fix version", "v0.9", "v1.0", now - timedelta(days=10)))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.scope_churn_7d_pct == 0.0


def test_scope_churn_7d_case_insensitive_release_name(db_session: Session) -> None:
    db_session.add(_release(name="Release 1.0"))
    db_session.add(_issue("P-1", "In Progress"))
    db_session.flush()

    now = datetime.now(UTC)
    # Value stored in different case — should still match
    db_session.add(_history("P-1", "fix version", "RELEASE 1.0", "v2.0", now - timedelta(days=1)))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.scope_churn_7d_pct == 100.0


def test_scope_churn_7d_supports_configured_changelog_alias(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.analytics_service.get_settings",
        lambda: Settings(jira_changelog_fix_version_fields="release scope"),
    )

    db_session.add(_release(name="v1.0"))
    db_session.add(_issue("P-1", "In Progress"))
    db_session.flush()

    now = datetime.now(UTC)
    db_session.add(_history("P-1", "release scope", "v0.9", "v1.0", now - timedelta(days=1)))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.scope_churn_7d_pct == 100.0


# ---------------------------------------------------------------------------
# reopen_rate_pct
# ---------------------------------------------------------------------------


def test_reopen_rate_pct_with_one_reopened(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "In Progress"))
    db_session.add(_issue("P-2", "To Do"))
    db_session.flush()

    # P-1 went Done → In Progress (reopened)
    db_session.add(_history("P-1", "status", "Done", "In Progress", datetime.now(UTC)))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.reopen_rate_pct == 50.0  # 1 reopened / 2 total


def test_reopen_rate_pct_no_reopens(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "Done"))
    db_session.flush()

    # Normal forward transition — not a reopen
    db_session.add(_history("P-1", "status", "In Progress", "Done", datetime.now(UTC)))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.reopen_rate_pct == 0.0


def test_reopen_rate_pct_only_counts_once_per_issue(db_session: Session) -> None:
    """An issue reopened multiple times counts only once in the numerator."""
    db_session.add(_release())
    db_session.add(_issue("P-1", "In Progress"))
    db_session.flush()

    now = datetime.now(UTC)
    # P-1 reopened twice
    db_session.add(_history("P-1", "status", "Done", "In Progress", now - timedelta(hours=4)))
    db_session.add(_history("P-1", "status", "Resolved", "In Progress", now - timedelta(hours=1)))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.reopen_rate_pct == 100.0  # 1 distinct reopened / 1 total


# ---------------------------------------------------------------------------
# median_cycle_time_days
# ---------------------------------------------------------------------------


def test_median_cycle_time_days_single_issue(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "Done"))
    db_session.flush()

    start = datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC)
    end = start + timedelta(days=3)
    db_session.add(_history("P-1", "status", "To Do", "In Progress", start))
    db_session.add(_history("P-1", "status", "In Progress", "Done", end))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.median_cycle_time_days == 3.0


def test_median_cycle_time_days_two_issues(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "Done"))
    db_session.add(_issue("P-2", "Done"))
    db_session.flush()

    base = datetime(2026, 4, 1, 0, 0, 0, tzinfo=UTC)
    # P-1: 2 days
    db_session.add(_history("P-1", "status", "To Do", "In Progress", base))
    db_session.add(_history("P-1", "status", "In Progress", "Done", base + timedelta(days=2)))
    # P-2: 4 days
    db_session.add(_history("P-2", "status", "To Do", "In Progress", base))
    db_session.add(_history("P-2", "status", "In Progress", "Done", base + timedelta(days=4)))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.median_cycle_time_days == 3.0  # median of [2, 4]


def test_median_cycle_time_days_skips_issues_without_in_progress(db_session: Session) -> None:
    """Issues that went directly to done without an in-progress transition are excluded."""
    db_session.add(_release())
    db_session.add(_issue("P-1", "Done"))
    db_session.flush()

    base = datetime(2026, 4, 1, 0, 0, 0, tzinfo=UTC)
    # Only a done transition, no in-progress
    db_session.add(_history("P-1", "status", "To Do", "Done", base + timedelta(days=1)))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.median_cycle_time_days is None


def test_median_cycle_time_days_no_history(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "Done"))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.median_cycle_time_days is None


# ---------------------------------------------------------------------------
# recompute_release_metrics — end-to-end snapshot persistence
# ---------------------------------------------------------------------------


def test_recompute_inserts_metric_snapshot_row(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "Done"))
    db_session.add(_issue("P-2", "In Progress", is_blocker=True))
    db_session.flush()

    snapshot = AnalyticsService().recompute_release_metrics(db_session, "R1")
    db_session.commit()

    stored = db_session.scalar(select(MetricSnapshot).where(MetricSnapshot.release_id == "R1"))
    assert stored is not None
    assert stored.open_blockers == 1
    assert stored.scope_completed_pct == 50.0
    assert stored is snapshot


def test_recompute_raises_for_unknown_release(db_session: Session) -> None:
    with pytest.raises(ValueError, match="Release not found"):
        AnalyticsService().recompute_release_metrics(db_session, "DOES_NOT_EXIST")
