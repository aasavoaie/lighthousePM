"""
Integration tests for the deterministic analytics pipeline.

Tests verify that the complete pipeline works correctly:
Jira ingestion → metric computation → signal generation → persistence

Each test uses factories to build realistic issue/history scenarios and verifies
that metrics are computed correctly and signals accurately reflect computed metrics.
"""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Issue, IssueHistory, MetricSnapshot, Release, ReleaseSignal
from app.services.analytics_service import AnalyticsService
from app.services.signal_service import SignalService


# ============================================================================
# Fixtures and Factories
# ============================================================================


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Create an in-memory SQLite session for each test."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_release(
    session: Session,
    release_id: str = "REL-1",
    name: str = "Release 1",
    project_key: str = "TEST",
) -> Release:
    """Factory: Create a Release."""
    now = datetime.now(UTC)
    release = Release(
        release_id=release_id,
        name=name,
        project_key=project_key,
        description=f"Test release {release_id}",
        status="active",
        start_date=now,
        release_date=None,
        created_at=now,
        updated_at=now,
    )
    session.add(release)
    session.commit()
    return release


def make_issue(
    session: Session,
    issue_key: str,
    release_id: str,
    issue_type: str = "Task",
    status: str = "To Do",
    priority: str = "Medium",
    is_blocker: bool = False,
    summary: str = "Test issue",
) -> Issue:
    """
    Factory: Create an Issue.

    Args:
        issue_key: Unique identifier (e.g., "TEST-1")
        release_id:FK to Release
        issue_type: "Task", "Bug", "Story", etc.
        status: Current status (e.g., "To Do", "In Progress", "Done")
        priority: "Low", "Medium", "High", "Highest", "Critical"
        is_blocker: If True, marks this as a blocking issue
        summary: Issue title
    """
    now = datetime.now(UTC)
    issue = Issue(
        issue_key=issue_key,
        summary=summary,
        issue_type=issue_type,
        status=status,
        priority=priority,
        assignee="test_user",
        release_id=release_id,
        is_blocker=is_blocker,
        jira_blocker_flag=True if is_blocker else None,
        jira_changelog_complete=True,
        created_at=now,
        updated_at=now,
    )
    session.add(issue)
    session.commit()
    return issue


def make_history(
    session: Session,
    issue_key: str,
    field_name: str,
    old_value: str | None,
    new_value: str,
    changed_at: datetime | None = None,
) -> IssueHistory:
    """
    Factory: Create an IssueHistory entry (status transition, field change, etc.).

    Args:
        issue_key: FK to Issue
        field_name: Field being changed (e.g., "status", "release", "priority")
        old_value: Previous value (can be None for first transition)
        new_value: New value
        changed_at: When the change happened (defaults to now)
    """
    if changed_at is None:
        changed_at = datetime.now(UTC)

    history = IssueHistory(
        issue_key=issue_key,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        changed_at=changed_at,
    )
    session.add(history)
    session.commit()
    return history


# ============================================================================
# Integration Tests
# ============================================================================


def test_pipeline_empty_release_signal_is_not_computed(db_session: Session) -> None:
    """
    Scenario: Release exists but has no issues.
    Expected: Count metrics are zero, churn is unavailable, and signal is not computed.
    """
    # Setup
    make_release(db_session, release_id="REL-1")

    # Execute: Recompute analytics then signal
    AnalyticsService().recompute_release_metrics(db_session, "REL-1")
    signal = SignalService().recompute_release_signal(db_session, "REL-1")

    # Verify: Metrics computed
    snapshot = db_session.query(MetricSnapshot).filter_by(release_id="REL-1").one()
    assert snapshot.open_blockers == 0
    assert snapshot.open_high_severity_bugs == 0
    assert snapshot.scope_completed_pct == 0.0
    assert snapshot.scope_churn_7d_pct is None
    assert snapshot.reopen_rate_pct is None
    assert snapshot.median_cycle_time_days is None

    # Verify: Signal not computed
    assert signal.signal == "NOT_COMPUTED"
    assert signal.reasons == ["No tickets are assigned to this release."]


def test_pipeline_red_from_open_blocker(db_session: Session) -> None:
    """
    Scenario: Release has one open blocker issue.
    Expected: open_blockers=1; the hard rule raises the final signal to RED.
    """
    # Setup
    make_release(db_session, release_id="REL-1")
    make_issue(
        db_session,
        issue_key="TEST-1",
        release_id="REL-1",
        status="In Progress",
        is_blocker=True,
    )

    # Execute
    AnalyticsService().recompute_release_metrics(db_session, "REL-1")
    signal = SignalService().recompute_release_signal(db_session, "REL-1")

    # Verify
    snapshot = db_session.query(MetricSnapshot).filter_by(release_id="REL-1").one()
    assert snapshot.open_blockers == 1

    assert signal.signal == "RED"
    assert any("blocker" in reason.lower() for reason in signal.reasons)


def test_pipeline_red_from_high_severity_bugs(db_session: Session) -> None:
    """
    Scenario: Release has 2 high-severity bugs.
    Expected: open_high_severity_bugs=2; the hard rule raises the final signal to RED.
    """
    # Setup
    make_release(db_session, release_id="REL-1")
    make_issue(
        db_session,
        issue_key="TEST-1",
        release_id="REL-1",
        issue_type="Bug",
        status="In Progress",
        priority="High",
    )
    make_issue(
        db_session,
        issue_key="TEST-2",
        release_id="REL-1",
        issue_type="Bug",
        status="In Progress",
        priority="Critical",
    )

    # Execute
    AnalyticsService().recompute_release_metrics(db_session, "REL-1")
    signal = SignalService().recompute_release_signal(db_session, "REL-1")

    # Verify
    snapshot = db_session.query(MetricSnapshot).filter_by(release_id="REL-1").one()
    assert snapshot.open_high_severity_bugs == 2

    assert signal.signal == "RED"
    assert any("high-severity" in reason.lower() for reason in signal.reasons)


def test_pipeline_red_from_scope_churn(db_session: Session) -> None:
    """
    Scenario: Issue's fix version is changed within 7 days.
    Expected: scope_churn_7d_pct=100%; the hard rule raises the final signal to RED.
    """
    # Setup
    now = datetime.now(UTC)
    make_release(db_session, release_id="REL-1", name="v1.0")

    # Create issue
    make_issue(
        db_session,
        issue_key="TEST-1",
        release_id="REL-1",
        status="In Progress",
    )

    # Simulate fix version change: Issue was reassigned from v0.9 to v1.0 within 7 days
    # This counts as scope churn (the issue was added to this release in last 7 days)
    make_history(
        db_session,
        "TEST-1",
        "fix version",
        "v0.9",
        "v1.0",
        changed_at=now - timedelta(days=3),
    )

    # Execute
    AnalyticsService().recompute_release_metrics(db_session, "REL-1")
    signal = SignalService().recompute_release_signal(db_session, "REL-1")

    # Verify
    snapshot = db_session.query(MetricSnapshot).filter_by(release_id="REL-1").order_by(MetricSnapshot.id.desc()).first()
    # 1 churned issue / 1 total = 100%
    assert snapshot.scope_churn_7d_pct == 100.0
    # The hard RED rule takes precedence over the GREEN confidence band.
    assert signal.signal == "RED"
    assert any("churn" in reason.lower() for reason in signal.reasons)


def test_pipeline_yellow_from_elevated_cycle_time(db_session: Session) -> None:
    """
    Scenario: Issue takes 10 days from In Progress to Done.
    Expected: median_cycle_time_days=10; the hard rule raises the final signal to YELLOW.
    """
    # Setup
    now = datetime.now(UTC)
    make_release(db_session, release_id="REL-1")

    # Create issue and simulate workflow
    make_issue(
        db_session,
        issue_key="TEST-1",
        release_id="REL-1",
        status="Done",
    )

    # Transition: To Do -> In Progress (day 0)
    make_history(
        db_session,
        "TEST-1",
        "status",
        "To Do",
        "In Progress",
        changed_at=now - timedelta(days=10),
    )

    # Transition: In Progress -> Done (day 10)
    make_history(
        db_session,
        "TEST-1",
        "status",
        "In Progress",
        "Done",
        changed_at=now,
    )

    # Execute
    AnalyticsService().recompute_release_metrics(db_session, "REL-1")
    signal = SignalService().recompute_release_signal(db_session, "REL-1")

    # Verify
    snapshot = db_session.query(MetricSnapshot).filter_by(release_id="REL-1").one()
    assert snapshot.median_cycle_time_days is not None
    assert snapshot.median_cycle_time_days >= 10.0

    assert signal.signal == "YELLOW"
    assert any("cycle" in reason.lower() for reason in signal.reasons)


def test_pipeline_red_from_reopened_issues(db_session: Session) -> None:
    """
    Scenario: One eligible issue has been reopened (Done -> In Progress).
    Expected: reopen_rate_pct = 100%; the hard rule raises the final signal to RED.
    """
    # Setup
    now = datetime.now(UTC)
    make_release(db_session, release_id="REL-1")

    # Create 10 issues
    # Create 2 issues
    make_issue(
        db_session,
        issue_key="TEST-1",
        release_id="REL-1",
        status="In Progress",
    )
    make_issue(
        db_session,
        issue_key="TEST-2",
        release_id="REL-1",
        status="To Do",
    )

    make_history(
        db_session,
        "TEST-1",
        "status",
        "To Do",
        "Done",
        changed_at=now - timedelta(hours=1),
    )
    make_history(
        db_session,
        "TEST-1",
        "status",
        "Done",
        "In Progress",
        changed_at=now,
    )
    # Execute
    AnalyticsService().recompute_release_metrics(db_session, "REL-1")
    signal = SignalService().recompute_release_signal(db_session, "REL-1")

    # Verify
    snapshot = db_session.query(MetricSnapshot).filter_by(release_id="REL-1").order_by(MetricSnapshot.id.desc()).first()
    assert snapshot.reopen_rate_pct == 100.0  # 1 event / 1 eligible ticket

    # The hard RED rule takes precedence over the GREEN confidence band.
    assert signal.signal == "RED"
    assert any("reopen" in reason.lower() for reason in signal.reasons)


def test_pipeline_multiple_triggers_red(db_session: Session) -> None:
    """
    Scenario: Release has both a blocker AND high-severity bugs.
    Expected: Both triggers detected; signal RED with both reasons.
    """
    # Setup
    make_release(db_session, release_id="REL-1")

    # Create blocker
    make_issue(
        db_session,
        issue_key="TEST-1",
        release_id="REL-1",
        status="In Progress",
        is_blocker=True,
    )

    # Create high-severity bug
    make_issue(
        db_session,
        issue_key="TEST-2",
        release_id="REL-1",
        issue_type="Bug",
        status="In Progress",
        priority="Critical",
    )

    # Create second high-severity bug (puts us over threshold of >1)
    make_issue(
        db_session,
        issue_key="TEST-3",
        release_id="REL-1",
        issue_type="Bug",
        status="In Progress",
        priority="High",
    )

    # Execute
    AnalyticsService().recompute_release_metrics(db_session, "REL-1")
    signal = SignalService().recompute_release_signal(db_session, "REL-1")

    # Verify: the explicit blocker and Critical-severity fallback are both blockers.
    snapshot = db_session.query(MetricSnapshot).filter_by(release_id="REL-1").one()
    assert snapshot.open_blockers == 2
    assert snapshot.open_high_severity_bugs == 2

    # Both reasons should be present
    assert signal.signal == "RED"
    assert len(signal.reasons) >= 2
    assert any("blocker" in reason.lower() for reason in signal.reasons)
    assert any("high-severity" in reason.lower() for reason in signal.reasons)


def test_pipeline_idempotency_same_signal(db_session: Session) -> None:
    """
    Scenario: Run recompute twice on same data.
    Expected: each new immutable metric snapshot has one append-only signal result.
    """
    # Setup
    make_release(db_session, release_id="REL-1")
    make_issue(
        db_session,
        issue_key="TEST-1",
        release_id="REL-1",
        status="In Progress",
        is_blocker=True,
    )

    # Execute first recompute
    AnalyticsService().recompute_release_metrics(db_session, "REL-1")
    signal1 = SignalService().recompute_release_signal(db_session, "REL-1")
    db_session.commit()  # Persist metrics and signal

    snapshot1_id = (
        db_session.query(MetricSnapshot)
        .filter_by(release_id="REL-1")
        .order_by(MetricSnapshot.id.desc())
        .first()
        .id
    )
    signal1_id = db_session.query(ReleaseSignal).filter_by(release_id="REL-1").one().id

    # Clear session to simulate new request
    db_session.expunge_all()

    # Execute second recompute
    AnalyticsService().recompute_release_metrics(db_session, "REL-1")
    signal2 = SignalService().recompute_release_signal(db_session, "REL-1")
    db_session.commit()  # Persist new metrics and signal

    snapshot2_id = (
        db_session.query(MetricSnapshot)
        .filter_by(release_id="REL-1")
        .order_by(MetricSnapshot.id.desc())
        .first()
        .id
    )
    signal_rows = (
        db_session.query(ReleaseSignal)
        .filter_by(release_id="REL-1")
        .order_by(ReleaseSignal.id)
        .all()
    )
    signal2_id = signal_rows[-1].id

    # Verify: Snapshots get new IDs (separate rows per recompute)
    assert snapshot1_id != snapshot2_id  # New snapshot created

    # Signals are append-only and linked to their source snapshots.
    assert signal1_id != signal2_id
    assert len(signal_rows) == 2
    assert [row.metric_snapshot_id for row in signal_rows] == [snapshot1_id, snapshot2_id]
    assert all(row.ruleset_version == 4 for row in signal_rows)

    # Both snapshots should have same metric values
    snapshot2 = db_session.query(MetricSnapshot).filter_by(release_id="REL-1").order_by(MetricSnapshot.id.desc()).first()
    assert snapshot2.open_blockers == 1

    # Signals should have identical information
    assert signal2.signal == "RED"
    assert signal2.reasons == signal1.reasons


def test_signal_recompute_is_idempotent_for_same_snapshot(db_session: Session) -> None:
    make_release(db_session, release_id="REL-1")
    make_issue(db_session, issue_key="TEST-1", release_id="REL-1", status="In Progress", is_blocker=True)
    snapshot = AnalyticsService().recompute_release_metrics(db_session, "REL-1")

    first = SignalService().recompute_release_signal(db_session, "REL-1")
    db_session.flush()
    second = SignalService().recompute_release_signal(db_session, "REL-1")
    db_session.commit()

    assert first.id == second.id
    assert first.metric_snapshot_id == snapshot.id
    assert db_session.query(ReleaseSignal).filter_by(release_id="REL-1").count() == 1


def test_pipeline_case_insensitive_priority_matching(db_session: Session) -> None:
    """
    Scenario: Create bugs with mixed-case priority names ("HIGH", "high", "High").
    Expected: All recognized as high-severity for metric calculation.
    """
    # Setup
    make_release(db_session, release_id="REL-1")

    # Create bugs with various case combinations of "High"
    for i, priority in enumerate(["HIGH", "high", "High"], start=1):
        make_issue(
            db_session,
            issue_key=f"TEST-{i}",
            release_id="REL-1",
            issue_type="Bug",
            status="In Progress",
            priority=priority,
        )

    # Execute
    AnalyticsService().recompute_release_metrics(db_session, "REL-1")
    signal = SignalService().recompute_release_signal(db_session, "REL-1")

    # Verify: All 3 bugs recognized as high-severity
    snapshot = db_session.query(MetricSnapshot).filter_by(release_id="REL-1").order_by(MetricSnapshot.id.desc()).first()
    assert snapshot.open_high_severity_bugs == 3

    # The hard RED rule takes precedence over the YELLOW confidence band.
    assert signal.signal == "RED"


def test_pipeline_data_consistency_metrics_signal_link(db_session: Session) -> None:
    """
    Scenario: Verify that signal reasons reference actual metric values.
    Expected: Reason text matches snapshot values (e.g., reason says "Open blockers: 2 > 0"
              when snapshot.open_blockers == 2).
    """
    # Setup
    make_release(db_session, release_id="REL-1")

    # Create 2 blockers
    for i in range(1, 3):
        make_issue(
            db_session,
            issue_key=f"TEST-{i}",
            release_id="REL-1",
            status="In Progress",
            is_blocker=True,
        )

    # Execute
    AnalyticsService().recompute_release_metrics(db_session, "REL-1")
    signal = SignalService().recompute_release_signal(db_session, "REL-1")

    # Verify
    snapshot = db_session.query(MetricSnapshot).filter_by(release_id="REL-1").one()
    assert snapshot.open_blockers == 2

    # Reason text should reference the actual metric value
    assert signal.signal == "RED"
    assert any("2" in reason and "blocker" in reason.lower() for reason in signal.reasons)
