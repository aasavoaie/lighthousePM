from types import SimpleNamespace

from app.services.confidence_breakdown_service import ConfidenceBreakdownService
from app.services.signal_service import SignalService


def test_release_breakdown_preserves_existing_confidence_score() -> None:
    snapshot = SimpleNamespace(
        open_blockers=1,
        open_high_severity_bugs=1,
        scope_churn_7d_pct=50.0,
        reopen_rate_pct=0.0,
        median_cycle_time_days=2.0,
    )

    breakdown = ConfidenceBreakdownService.build_release_breakdown(snapshot)

    assert breakdown.totalScore == SignalService._confidence_score_for_snapshot(snapshot)
    assert [component.name for component in breakdown.components] == ["Delivery", "Quality", "Flow", "Risk"]
    assert [(component.score, component.maxScore) for component in breakdown.components] == [
        (14.0, 30.0),
        (21.0, 30.0),
        (20.0, 20.0),
        (0.0, 20.0),
    ]
    assert breakdown.components[0].status == "critical"
    assert "Scope churn" in breakdown.components[0].explanation


def test_release_breakdown_scores_all_healthy_components_full() -> None:
    snapshot = SimpleNamespace(
        open_blockers=0,
        open_high_severity_bugs=0,
        scope_churn_7d_pct=0.0,
        reopen_rate_pct=0.0,
        median_cycle_time_days=None,
    )

    breakdown = ConfidenceBreakdownService.build_release_breakdown(snapshot)

    assert breakdown.totalScore == 100.0
    assert all(component.status == "good" for component in breakdown.components)
    assert sum(component.score for component in breakdown.components) == 100.0


def test_sprint_breakdown_uses_delivery_confidence_components() -> None:
    breakdown = ConfidenceBreakdownService.build_sprint_breakdown(
        score=63.4,
        components={
            "progress_alignment": 60.0,
            "velocity_fit": 49.0,
            "scope_stability": 54.0,
            "blocker_penalty": 100.0,
        },
        inputs={
            "completed_scope_pct": 40.0,
            "time_elapsed_pct": 60.0,
            "historical_velocity": 10.0,
            "scope_change_count": 2,
            "blocked_issue_ratio": 0.0,
        },
    )

    assert breakdown.totalScore == 63.4
    assert [component.id for component in breakdown.components] == [
        "progress_alignment",
        "velocity_fit",
        "scope_stability",
        "blocker_health",
    ]
    assert [component.score for component in breakdown.components] == [60.0, 49.0, 54.0, 100.0]
    assert breakdown.components[-1].status == "good"
    assert breakdown.components[1].status == "critical"
