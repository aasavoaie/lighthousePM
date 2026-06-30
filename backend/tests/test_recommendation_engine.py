from types import SimpleNamespace

from app.schemas.availability import MetricAvailability, MetricAvailabilityContext, MetricAvailabilityItem
from app.services.recommendation_engine import RecommendationEngine


def _availability(available_by_metric: dict[str, bool]) -> MetricAvailability:
    return MetricAvailability(
        context=MetricAvailabilityContext(
            has_tickets=True,
            has_story_points=False,
            has_completed_tickets=False,
            has_release_scope=True,
            has_sprint_scope=False,
            has_changelog=False,
        ),
        metrics={
            metric_name: MetricAvailabilityItem(
                available=is_available,
                reason=None if is_available else "No Jira changelog history is available for this scope.",
                depends_on=[],
            )
            for metric_name, is_available in available_by_metric.items()
        },
    )


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


def test_release_recommendations_skip_unavailable_metrics() -> None:
    snapshot = SimpleNamespace(
        open_blockers=2,
        open_high_severity_bugs=1,
        scope_churn_7d_pct=40.0,
        reopen_rate_pct=35.0,
        median_cycle_time_days=18.0,
    )
    availability = _availability(
        {
            "open_blockers": True,
            "open_high_severity_bugs": True,
            "scope_churn_7d_pct": False,
            "reopen_rate_pct": False,
            "median_cycle_time_days": False,
        }
    )

    recommendations = RecommendationEngine.build_release_recommendations(
        snapshot,
        metric_availability=availability,
    )

    assert [item.title for item in recommendations] == [
        "Resolve blockers",
        "Resolve critical defects",
    ]


def test_release_recommendations_are_empty_when_all_triggering_metrics_are_unavailable() -> None:
    snapshot = SimpleNamespace(
        open_blockers=2,
        open_high_severity_bugs=1,
        scope_churn_7d_pct=40.0,
        reopen_rate_pct=35.0,
        median_cycle_time_days=18.0,
    )
    availability = _availability(
        {
            "open_blockers": False,
            "open_high_severity_bugs": False,
            "scope_churn_7d_pct": False,
            "reopen_rate_pct": False,
            "median_cycle_time_days": False,
        }
    )

    recommendations = RecommendationEngine.build_release_recommendations(
        snapshot,
        metric_availability=availability,
    )

    assert recommendations == []


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


def test_sprint_recommendations_skip_workload_concentration_without_story_points() -> None:
    snapshot = SimpleNamespace(
        completed_scope_pct=60.0,
        open_blockers=0,
        open_high_severity_bugs=0,
        median_cycle_time_days=4.0,
        reopen_rate_pct=0.0,
        delivery_confidence_components={},
        delivery_confidence_inputs={},
    )
    sprint_issues = [
        SimpleNamespace(assignee="Ava", story_points=None, status="In Progress"),
        SimpleNamespace(assignee="Ava", story_points=None, status="To Do"),
        SimpleNamespace(assignee="Noah", story_points=None, status="In Progress"),
    ]

    recommendations = RecommendationEngine.build_sprint_recommendations(
        snapshot,
        sprint_issues=sprint_issues,
    )

    assert [item.title for item in recommendations] == ["Complete committed work"]


def test_sprint_recommendations_can_skip_story_point_rules() -> None:
    snapshot = SimpleNamespace(
        completed_scope_pct=60.0,
        open_blockers=1,
        open_high_severity_bugs=0,
        median_cycle_time_days=4.0,
        reopen_rate_pct=0.0,
        delivery_confidence_components={"progress_alignment": 25.0, "scope_stability": 40.0},
        delivery_confidence_inputs={"remaining_effective_points": 8.0, "scope_change_count": 3},
    )

    recommendations = RecommendationEngine.build_sprint_recommendations(
        snapshot,
        sprint_issues=[],
        include_story_point_rules=False,
    )

    assert [item.title for item in recommendations] == ["Resolve sprint blockers"]


def test_sprint_workload_concentration_ignores_unpointed_issues() -> None:
    snapshot = SimpleNamespace(
        completed_scope_pct=100.0,
        open_blockers=0,
        open_high_severity_bugs=0,
        median_cycle_time_days=4.0,
        reopen_rate_pct=0.0,
        delivery_confidence_components={},
        delivery_confidence_inputs={},
    )
    sprint_issues = [
        SimpleNamespace(assignee="Ava", story_points=None, status="In Progress"),
        SimpleNamespace(assignee="Noah", story_points=8.0, status="To Do"),
        SimpleNamespace(assignee="Mira", story_points=12.0, status="In Progress"),
    ]

    recommendations = RecommendationEngine.build_sprint_recommendations(
        snapshot,
        sprint_issues=sprint_issues,
    )

    assert [item.title for item in recommendations] == ["Reduce workload concentration"]


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
