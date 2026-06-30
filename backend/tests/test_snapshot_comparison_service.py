from types import SimpleNamespace

from app.services.snapshot_comparison_service import SnapshotComparisonService


def _release_snapshot(**overrides):
    values = {
        "open_blockers": 0,
        "open_high_severity_bugs": 0,
        "scope_churn_7d_pct": 0.0,
        "reopen_rate_pct": 0.0,
        "median_cycle_time_days": 2.0,
        "completed_tickets": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _sprint_snapshot(**overrides):
    values = {
        "delivery_confidence_score": 100.0,
        "delivery_confidence_components": {
            "progress_alignment": 100.0,
            "velocity_fit": 100.0,
            "blocker_penalty": 100.0,
            "scope_stability": 100.0,
        },
        "reopen_rate_pct": 0.0,
        "bugs_created_during_sprint": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_release_comparison_explains_confidence_increase() -> None:
    previous = _release_snapshot(open_blockers=1, open_high_severity_bugs=1, completed_tickets=2)
    current = _release_snapshot(open_blockers=0, open_high_severity_bugs=0, completed_tickets=5)

    comparison = SnapshotComparisonService.compare_release_snapshots(current, previous)

    assert comparison.confidence_delta == 37.0
    assert comparison.contributors[0].metric == "open_blockers"
    assert comparison.contributors[0].delta == -1.0
    assert comparison.contributors[0].impact == 28.0
    assert comparison.contributors[0].direction == "down"
    assert any(item.metric == "completed_tickets" and item.impact == 0.0 for item in comparison.contributors)


def test_release_comparison_explains_confidence_decrease() -> None:
    previous = _release_snapshot()
    current = _release_snapshot(open_blockers=1, reopen_rate_pct=16.0)

    comparison = SnapshotComparisonService.compare_release_snapshots(current, previous)

    assert comparison.confidence_delta == -34.0
    assert [(item.metric, item.impact) for item in comparison.contributors[:2]] == [
        ("open_blockers", -28.0),
        ("reopen_rate_pct", -6.0),
    ]


def test_release_comparison_returns_no_contributors_when_unchanged() -> None:
    previous = _release_snapshot(open_blockers=1, reopen_rate_pct=12.0)
    current = _release_snapshot(open_blockers=1, reopen_rate_pct=12.0)

    comparison = SnapshotComparisonService.compare_release_snapshots(current, previous)

    assert comparison.confidence_delta == 0.0
    assert comparison.contributors == []
    assert SnapshotComparisonService.primary_driver(comparison) == "No material change"


def test_sprint_comparison_uses_delivery_confidence_component_weights() -> None:
    previous = _sprint_snapshot(
        delivery_confidence_score=62.0,
        delivery_confidence_components={
            "progress_alignment": 50.0,
            "velocity_fit": 60.0,
            "blocker_penalty": 70.0,
            "scope_stability": 100.0,
        },
    )
    current = _sprint_snapshot(
        delivery_confidence_score=74.0,
        delivery_confidence_components={
            "progress_alignment": 70.0,
            "velocity_fit": 70.0,
            "blocker_penalty": 75.0,
            "scope_stability": 100.0,
        },
        reopen_rate_pct=5.0,
    )

    comparison = SnapshotComparisonService.compare_sprint_snapshots(current, previous)

    assert comparison.confidence_delta == 12.0
    assert comparison.contributors[0].metric == "progress_alignment"
    assert comparison.contributors[0].impact == 8.0
    assert any(item.metric == "reopen_rate_pct" and item.impact == 0.0 for item in comparison.contributors)


def test_sprint_comparison_keeps_confidence_delta_unavailable_when_confidence_is_missing() -> None:
    previous = _sprint_snapshot(delivery_confidence_score=None, delivery_confidence_components=None)
    current = _sprint_snapshot(delivery_confidence_score=None, delivery_confidence_components=None)

    comparison = SnapshotComparisonService.compare_sprint_snapshots(current, previous)

    assert comparison.confidence_delta is None
    assert comparison.contributors == []
