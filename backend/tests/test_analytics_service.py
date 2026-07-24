"""Tests for AnalyticsService — uses in-memory SQLite via StaticPool."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db.base import Base
from app.models import Issue, IssueHistory, MetricSnapshot, Release
from app.services.analytics_service import AnalyticsService
from app.services.jira_field_mapper import JiraFieldMapper

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


def _release(release_id: str = "R1", name: str = "v1.0", project_key: str = "PROJ") -> Release:
    return Release(
        release_id=release_id,
        name=name,
        project_key=project_key,
        status="unreleased",
    )


def _issue(
    key: str,
    status: str,
    issue_type: str = "Story",
    priority: str = "Medium",
    release_id: str | None = "R1",
    is_blocker: bool = False,
    jira_blocker_flag: bool | None = None,
    jira_changelog_complete: bool = True,
) -> Issue:
    return Issue(
        issue_key=key,
        summary=key,
        issue_type=issue_type,
        status=status,
        priority=priority,
        release_id=release_id,
        is_blocker=is_blocker,
        jira_blocker_flag=jira_blocker_flag if jira_blocker_flag is not None else (True if is_blocker else None),
        jira_changelog_complete=jira_changelog_complete,
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
    assert result.open_blocker_issue_keys == ["P-1", "P-2"]


def test_open_blockers_empty_release(db_session: Session) -> None:
    db_session.add(_release())
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.open_blockers == 0
    assert result.open_blocker_issue_keys == []


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
    assert result.open_high_severity_bug_issue_keys == ["P-1", "P-2"]


def test_open_high_severity_bugs_case_insensitive(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "in progress", issue_type="BUG", priority="HIGHEST"))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.open_high_severity_bugs == 1
    assert result.open_high_severity_bug_issue_keys == ["P-1"]


def test_release_metrics_use_effective_classifications_and_record_them(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom_classifications = {
        "JIRA_DONE_STATUSES": "Released",
        "JIRA_IN_PROGRESS_STATUSES": "Building",
        "JIRA_HIGH_SEVERITY_VALUES": "Sev-1",
        "JIRA_BUG_ISSUE_TYPES": "Defect",
        "JIRA_BLOCKER_ISSUE_TYPES": "Impediment",
        "JIRA_BLOCKER_SEVERITY_VALUES": "Stop-ship",
        "JIRA_BLOCKED_STATUSES": "Waiting",
        "JIRA_FIELD_STORY_POINTS": "",
        "JIRA_FIELD_SEVERITY": "priority",
        "JIRA_FIELD_RELEASE": "fixVersions",
        "JIRA_FIELD_SPRINT": "",
        "JIRA_FIELD_BLOCKER": "",
        "JIRA_BLOCKER_TRUE_VALUES": "true,yes,1,blocker",
    }
    for name, value in custom_classifications.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()

    db_session.add(_release())
    db_session.add(_issue("P-1", "Building", issue_type="Impediment"))
    db_session.add(_issue("P-2", "Building", issue_type="Defect", priority="Sev-1"))
    db_session.add(_issue("P-3", "Released"))
    db_session.flush()

    try:
        result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    finally:
        get_settings.cache_clear()

    assert result.open_blocker_issue_keys == ["P-1"]
    assert result.open_high_severity_bug_issue_keys == ["P-2"]
    assert result.completed_tickets == 1
    assert result.scope_completed_pct == pytest.approx(33.33)
    assert result.calculation_provenance["classification"] == {
        "done_statuses": ["released"],
        "in_progress_statuses": ["building"],
        "high_severity_values": ["sev-1"],
        "bug_issue_types": ["defect"],
        "blocker_issue_types": ["impediment"],
        "blocker_severity_values": ["stop-ship"],
        "blocked_statuses": ["waiting"],
        "severity_field": "priority",
        "story_points_field": "",
        "release_field": "fixVersions",
        "sprint_field": "",
        "blocker_field": "",
        "blocker_true_values": ["1", "blocker", "true", "yes"],
    }


# ---------------------------------------------------------------------------
# scope_completed_pct
# ---------------------------------------------------------------------------


def test_scope_completed_pct_empty_release(db_session: Session) -> None:
    db_session.add(_release())
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.scope_completed_pct == 0.0
    assert result.completed_tickets == 0


def test_scope_completed_pct_partial(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "Done"))
    db_session.add(_issue("P-2", "Closed"))
    db_session.add(_issue("P-3", "In Progress"))
    db_session.add(_issue("P-4", "To Do"))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.scope_completed_pct == 50.0
    assert result.completed_tickets == 2


def test_scope_completed_pct_all_done(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "Done"))
    db_session.add(_issue("P-2", "Resolved"))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.scope_completed_pct == 100.0
    assert result.completed_tickets == 2


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
    assert result.scope_added_7d_count == 1
    assert result.scope_removed_7d_count == 1
    evidence = result.calculation_provenance["scope_churn_7d"]
    assert evidence["current_scope_issue_keys"] == ["P-1", "P-2"]
    assert evidence["observed_scope_issue_keys"] == ["P-1", "P-2"]
    assert evidence["observed_scope_denominator"] == 2
    assert evidence["churned_issue_keys"] == ["P-1", "P-2"]
    assert evidence["added_issue_keys"] == ["P-1"]
    assert evidence["removed_issue_keys"] == ["P-2"]
    assert evidence["incomplete_project_changelog_issue_keys"] == []
    assert evidence["normalized_release_value"] == "v1.0"


def test_scope_churn_uses_inclusive_snapshot_boundaries_and_distinct_union(
    db_session: Session,
) -> None:
    db_session.add(_release(name="v1.0"))
    db_session.add(_issue("PROJ-1", "In Progress"))
    db_session.add(_issue("PROJ-2", "To Do", release_id=None))
    db_session.flush()

    snapshot_at = datetime(2026, 7, 17, 12, tzinfo=UTC)
    window_start = snapshot_at - timedelta(days=7)
    db_session.add(_history("PROJ-1", " fix version ", "v0.9", " V1.0 ", window_start))
    db_session.add(_history("PROJ-1", "fixversion", "v1.0", "v2.0", snapshot_at))
    db_session.add(
        _history("PROJ-2", "fix version", "v0.9", "v1.0", window_start - timedelta(microseconds=1))
    )
    db_session.add(
        _history("PROJ-2", "fix version", "v0.9", "v1.0", snapshot_at + timedelta(microseconds=1))
    )
    db_session.flush()

    result = AnalyticsService._compute_release_scope_churn_7d(
        session=db_session,
        release_id="R1",
        project_key="PROJ",
        release_name="v1.0",
        field_mapper=JiraFieldMapper(Settings(_env_file=None)),
        snapshot_at=snapshot_at,
    )

    assert result["status"] == "COMPUTED"
    assert result["scope_churn_7d_pct"] == 100.0
    assert result["scope_added_7d_count"] == 1
    assert result["scope_removed_7d_count"] == 1
    assert result["evidence"]["churned_issue_keys"] == ["PROJ-1"]
    assert result["evidence"]["added_issue_keys"] == ["PROJ-1"]
    assert result["evidence"]["removed_issue_keys"] == ["PROJ-1"]
    assert result["evidence"]["window_start"] == window_start.isoformat()
    assert result["evidence"]["window_end"] == snapshot_at.isoformat()


def test_scope_churn_computes_removal_only_observed_scope(db_session: Session) -> None:
    db_session.add(_release(name="v1.0"))
    db_session.add(_issue("PROJ-1", "To Do", release_id=None))
    db_session.flush()
    snapshot_at = datetime(2026, 7, 17, 12, tzinfo=UTC)
    db_session.add(
        _history("PROJ-1", "fix version", "v1.0", "v2.0", snapshot_at - timedelta(days=1))
    )
    db_session.flush()

    result = AnalyticsService._compute_release_scope_churn_7d(
        session=db_session,
        release_id="R1",
        project_key="PROJ",
        release_name="v1.0",
        field_mapper=JiraFieldMapper(Settings(_env_file=None)),
        snapshot_at=snapshot_at,
    )

    assert result["status"] == "COMPUTED"
    assert result["scope_churn_7d_pct"] == 100.0
    assert result["scope_added_7d_count"] == 0
    assert result["scope_removed_7d_count"] == 1
    assert result["evidence"]["current_scope_issue_keys"] == []
    assert result["evidence"]["observed_scope_issue_keys"] == ["PROJ-1"]


def test_scope_churn_is_partial_with_project_wide_incomplete_history(
    db_session: Session,
) -> None:
    db_session.add(_release(name="v1.0"))
    db_session.add(_issue("PROJ-1", "To Do"))
    db_session.add(
        _issue(
            "PROJ-2",
            "To Do",
            release_id=None,
            jira_changelog_complete=False,
        )
    )
    db_session.flush()
    snapshot_at = datetime(2026, 7, 17, 12, tzinfo=UTC)
    db_session.add(
        _history("PROJ-2", "fix version", "v0.9", "v1.0", snapshot_at - timedelta(days=1))
    )
    db_session.flush()

    result = AnalyticsService._compute_release_scope_churn_7d(
        session=db_session,
        release_id="R1",
        project_key="PROJ",
        release_name="v1.0",
        field_mapper=JiraFieldMapper(Settings(_env_file=None)),
        snapshot_at=snapshot_at,
    )

    assert result["status"] == "PARTIAL"
    assert result["scope_churn_7d_pct"] is None
    assert result["scope_added_7d_count"] == 1
    assert result["scope_removed_7d_count"] == 0
    assert result["missing_issue_keys"] == ["PROJ-2"]
    assert result["evidence"]["observed_scope_issue_keys"] == ["PROJ-1", "PROJ-2"]
    assert result["evidence"]["observed_scope_denominator"] == 2


def test_scope_churn_is_not_computed_without_observed_scope(db_session: Session) -> None:
    db_session.add(_release(name="v1.0"))
    db_session.add(_issue("PROJ-1", "To Do", release_id=None))
    db_session.flush()
    snapshot_at = datetime(2026, 7, 17, 12, tzinfo=UTC)

    result = AnalyticsService._compute_release_scope_churn_7d(
        session=db_session,
        release_id="R1",
        project_key="PROJ",
        release_name="v1.0",
        field_mapper=JiraFieldMapper(Settings(_env_file=None)),
        snapshot_at=snapshot_at,
    )

    assert result["status"] == "NOT_COMPUTED"
    assert result["scope_churn_7d_pct"] is None
    assert result["scope_added_7d_count"] == 0
    assert result["scope_removed_7d_count"] == 0
    assert result["evidence"]["observed_scope_issue_keys"] == []
    assert result["evidence"]["observed_scope_denominator"] == 0


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
    assert result.scope_added_7d_count == 0
    assert result.scope_removed_7d_count == 0


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
    assert result.scope_added_7d_count == 0
    assert result.scope_removed_7d_count == 1


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
    assert result.scope_added_7d_count == 1
    assert result.scope_removed_7d_count == 0


def test_scope_churn_7d_ignores_same_release_name_from_other_project(db_session: Session) -> None:
    db_session.add(_release(release_id="R1", name="v1.0", project_key="PROJ"))
    db_session.add(_release(release_id="R2", name="v1.0", project_key="OTHER"))
    db_session.add(_issue("PROJ-1", "In Progress", release_id="R1"))
    db_session.add(_issue("OTHER-1", "In Progress", release_id="R2"))
    db_session.flush()

    now = datetime.now(UTC)
    db_session.add(_history("PROJ-1", "fix version", "v0.9", "v1.0", now - timedelta(days=1)))
    db_session.add(_history("OTHER-1", "fix version", "v0.9", "v1.0", now - timedelta(days=1)))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")

    assert result.scope_churn_7d_pct == 100.0
    assert result.scope_added_7d_count == 1
    assert result.scope_removed_7d_count == 0


# ---------------------------------------------------------------------------
# reopen_rate_pct
# ---------------------------------------------------------------------------


def test_reopen_rate_pct_with_one_reopened(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "In Progress"))
    db_session.add(_issue("P-2", "To Do"))
    db_session.flush()

    now = datetime.now(UTC)
    db_session.add(_history("P-1", "status", "To Do", "Done", now - timedelta(hours=1)))
    db_session.add(_history("P-1", "status", "Done", "In Progress", now))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.reopen_rate_pct == 100.0  # 1 event / 1 eligible ticket


def test_reopen_rate_pct_no_reopens(db_session: Session) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "Done"))
    db_session.flush()

    # Normal forward transition — not a reopen
    db_session.add(_history("P-1", "status", "In Progress", "Done", datetime.now(UTC)))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.reopen_rate_pct == 0.0


def test_reopen_rate_pct_counts_every_distinct_event_per_issue(db_session: Session) -> None:
    """An issue reopened multiple times contributes every distinct event."""
    db_session.add(_release())
    db_session.add(_issue("P-1", "In Progress"))
    db_session.flush()

    now = datetime.now(UTC)
    db_session.add(_history("P-1", "status", "To Do", "Done", now - timedelta(hours=5)))
    db_session.add(_history("P-1", "status", "Done", "In Progress", now - timedelta(hours=4)))
    db_session.add(_history("P-1", "status", "In Progress", "Resolved", now - timedelta(hours=2)))
    db_session.add(_history("P-1", "status", "Resolved", "In Progress", now - timedelta(hours=1)))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")
    assert result.reopen_rate_pct == 200.0  # 2 events / 1 eligible ticket
    reopen_availability = result.calculation_provenance["availability"]["metrics"][
        "reopen_rate_pct"
    ]
    assert reopen_availability["status"] == "COMPUTED"
    assert reopen_availability["explanations"] == [
        "Ticket P-1 was counted 2 times because it was reopened 2 times."
    ]
    reopen_evidence = result.calculation_provenance["metric_evidence"]["reopen_rate_pct"]
    assert reopen_evidence["eligible_ticket_count"] == 1
    assert reopen_evidence["reopen_event_count"] == 2
    assert reopen_evidence["event_count_by_issue"] == {"P-1": 2}


def test_reopen_rate_partial_persists_null_with_confirmed_provenance(
    db_session: Session,
) -> None:
    db_session.add(_release())
    db_session.add(_issue("P-1", "Done", jira_changelog_complete=False))
    db_session.flush()

    now = datetime.now(UTC)
    db_session.add(_history("P-1", "status", "To Do", "Done", now - timedelta(hours=2)))
    db_session.add(_history("P-1", "status", "Done", "In Progress", now - timedelta(hours=1)))
    db_session.flush()

    result = AnalyticsService().recompute_release_metrics(db_session, "R1")

    assert result.reopen_rate_pct is None
    availability = result.calculation_provenance["availability"]["metrics"]["reopen_rate_pct"]
    assert availability["status"] == "PARTIAL"
    assert availability["available"] is False
    assert availability["missing_issue_keys"] == ["P-1"]
    evidence = result.calculation_provenance["metric_evidence"]["reopen_rate_pct"]
    assert evidence["eligible_ticket_count"] == 1
    assert evidence["reopen_event_count"] == 1


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
    assert stored.open_blocker_issue_keys == ["P-2"]
    assert stored.scope_completed_pct == 50.0
    assert stored.completed_tickets == 1
    assert stored is snapshot


def test_recompute_raises_for_unknown_release(db_session: Session) -> None:
    with pytest.raises(ValueError, match="Release not found"):
        AnalyticsService().recompute_release_metrics(db_session, "DOES_NOT_EXIST")
