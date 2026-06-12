from types import SimpleNamespace

from app.services.recommendation_engine import RecommendationEngine


def test_release_recommendations_are_generated_and_prioritized() -> None:
    snapshot = SimpleNamespace(
        open_blockers=2,
        open_high_severity_bugs=1,
        scope_churn_7d_pct=0.0,
        reopen_rate_pct=12.0,
        median_cycle_time_days=None,
    )

    recommendations = RecommendationEngine.build_release_recommendations(snapshot)

    assert [item.title for item in recommendations] == [
        "Resolve blockers",
        "Resolve critical defects",
        "Reduce reopen rate",
    ]
    assert [item.confidenceImpact for item in recommendations] == [10, 8, 6]
    assert [item.priority for item in recommendations] == [1, 2, 3]
    assert [item.category for item in recommendations] == ["Risk", "Quality", "Quality"]


def test_release_recommendations_are_empty_when_metrics_are_within_thresholds() -> None:
    snapshot = SimpleNamespace(
        open_blockers=0,
        open_high_severity_bugs=0,
        scope_churn_7d_pct=10.0,
        reopen_rate_pct=10.0,
        median_cycle_time_days=7.0,
    )

    assert RecommendationEngine.build_release_recommendations(snapshot) == []


def test_sprint_recommendations_include_scope_work_and_concentration() -> None:
    snapshot = SimpleNamespace(
        completed_scope_pct=60.0,
        open_blockers=0,
        open_high_severity_bugs=0,
        median_cycle_time_days=4.0,
        reopen_rate_pct=0.0,
        delivery_confidence_components={
            "progress_alignment": 70.0,
            "velocity_fit": 80.0,
            "blocker_penalty": 100.0,
            "scope_stability": 82.0,
        },
        delivery_confidence_inputs={
            "remaining_effective_points": 8.0,
            "scope_change_count": 3,
        },
    )
    sprint_issues = [
        SimpleNamespace(assignee="Ava", story_points=8.0, status="In Progress"),
        SimpleNamespace(assignee="Noah", story_points=2.0, status="To Do"),
        SimpleNamespace(assignee="Mira", story_points=13.0, status="Done"),
    ]

    recommendations = RecommendationEngine.build_sprint_recommendations(
        snapshot,
        sprint_issues=sprint_issues,
    )

    assert [item.title for item in recommendations] == [
        "Reduce scope changes",
        "Complete committed work",
        "Reduce workload concentration",
    ]
    assert [item.confidenceImpact for item in recommendations] == [7, 5, 4]
    assert [item.priority for item in recommendations] == [1, 2, 3]


def test_sprint_recommendations_sort_ties_by_rule_order() -> None:
    snapshot = SimpleNamespace(
        completed_scope_pct=100.0,
        open_blockers=0,
        open_high_severity_bugs=1,
        median_cycle_time_days=8.0,
        reopen_rate_pct=12.0,
        delivery_confidence_components={},
        delivery_confidence_inputs={},
    )

    recommendations = RecommendationEngine.build_sprint_recommendations(snapshot)

    assert [item.title for item in recommendations] == [
        "Resolve sprint defects",
        "Reduce sprint cycle time",
        "Reduce reopened sprint work",
    ]
    assert [item.confidenceImpact for item in recommendations] == [5, 4, 4]
    assert [item.priority for item in recommendations] == [1, 2, 3]
