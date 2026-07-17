from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Issue, IssueHistory, IssueSprint
from app.schemas.availability import MetricAvailability, MetricAvailabilityContext, MetricAvailabilityItem
from app.services.jira_field_mapper import JiraFieldMapper

COMPUTATION_STATUS_COMPUTED = "COMPUTED"
COMPUTATION_STATUS_PARTIAL = "PARTIAL"
COMPUTATION_STATUS_NOT_COMPUTED = "NOT_COMPUTED"
UNAVAILABLE_REASON_NO_TICKETS = "No tickets are available for this scope."
UNAVAILABLE_REASON_NO_STORY_POINTS = (
    "Delivery confidence requires at least 50% of sprint tickets to have valid story points."
)
UNAVAILABLE_REASON_NO_CHANGELOG = "No Jira changelog history is available for this scope."
UNAVAILABLE_REASON_RELEASE_EMPTY = UNAVAILABLE_REASON_NO_TICKETS
UNAVAILABLE_REASON_SPRINT_EMPTY = UNAVAILABLE_REASON_NO_TICKETS
UNAVAILABLE_REASON_NOT_COMPUTED = "Metrics have not been computed yet."

DEPENDENCY_TICKET_COUNT = "ticket_count"
DEPENDENCY_STORY_POINTS = "story_points"
DEPENDENCY_COMPLETED_TICKETS = "completed_tickets"
DEPENDENCY_HISTORY_CHANGELOG = "history_changelog"
DEPENDENCY_RELEASE_ASSIGNMENT = "release_assignment"
DEPENDENCY_SPRINT_ASSIGNMENT = "sprint_assignment"

RELEASE_METRIC_DEPENDENCIES: dict[str, list[str]] = {
    "open_blockers": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_RELEASE_ASSIGNMENT],
    "open_high_severity_bugs": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_RELEASE_ASSIGNMENT],
    "scope_completed_pct": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_RELEASE_ASSIGNMENT],
    "completed_tickets": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_RELEASE_ASSIGNMENT],
    "scope_churn_7d_pct": [
        DEPENDENCY_TICKET_COUNT,
        DEPENDENCY_HISTORY_CHANGELOG,
        DEPENDENCY_RELEASE_ASSIGNMENT,
    ],
    "scope_added_7d_count": [
        DEPENDENCY_TICKET_COUNT,
        DEPENDENCY_HISTORY_CHANGELOG,
        DEPENDENCY_RELEASE_ASSIGNMENT,
    ],
    "scope_removed_7d_count": [
        DEPENDENCY_TICKET_COUNT,
        DEPENDENCY_HISTORY_CHANGELOG,
        DEPENDENCY_RELEASE_ASSIGNMENT,
    ],
    "median_cycle_time_days": [
        DEPENDENCY_TICKET_COUNT,
        DEPENDENCY_COMPLETED_TICKETS,
        DEPENDENCY_HISTORY_CHANGELOG,
        DEPENDENCY_RELEASE_ASSIGNMENT,
    ],
    "reopen_rate_pct": [
        DEPENDENCY_TICKET_COUNT,
        DEPENDENCY_HISTORY_CHANGELOG,
        DEPENDENCY_RELEASE_ASSIGNMENT,
    ],
    "confidence_score": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_RELEASE_ASSIGNMENT],
    "gates_passed_count": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_RELEASE_ASSIGNMENT],
    "readiness_pct": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_RELEASE_ASSIGNMENT],
}

SPRINT_METRIC_DEPENDENCIES: dict[str, list[str]] = {
    "committed_scope": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_SPRINT_ASSIGNMENT],
    "completed_scope_pct": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_SPRINT_ASSIGNMENT],
    "open_blockers": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_SPRINT_ASSIGNMENT],
    "open_high_severity_bugs": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_SPRINT_ASSIGNMENT],
    "bugs_created_during_sprint": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_SPRINT_ASSIGNMENT],
    "in_progress_count": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_SPRINT_ASSIGNMENT],
    "not_started_count": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_SPRINT_ASSIGNMENT],
    "rollover_count": [DEPENDENCY_TICKET_COUNT, DEPENDENCY_SPRINT_ASSIGNMENT],
    "median_cycle_time_days": [
        DEPENDENCY_TICKET_COUNT,
        DEPENDENCY_COMPLETED_TICKETS,
        DEPENDENCY_HISTORY_CHANGELOG,
        DEPENDENCY_SPRINT_ASSIGNMENT,
    ],
    "reopen_rate_pct": [
        DEPENDENCY_TICKET_COUNT,
        DEPENDENCY_HISTORY_CHANGELOG,
        DEPENDENCY_SPRINT_ASSIGNMENT,
    ],
    "delivery_confidence_score": [
        DEPENDENCY_TICKET_COUNT,
        DEPENDENCY_STORY_POINTS,
        DEPENDENCY_SPRINT_ASSIGNMENT,
    ],
}


class MetricAvailabilityService:
    """Build deterministic metric availability rules for API responses."""

    @staticmethod
    def build_release_availability(
        session: Session,
        release_id: str,
        field_mapper: JiraFieldMapper,
    ) -> MetricAvailability:
        release_issue_keys = select(Issue.issue_key).where(Issue.release_id == release_id)
        total_tickets = _scalar_count(
            session,
            select(func.count()).select_from(Issue).where(Issue.release_id == release_id),
        )
        story_point_tickets = _scalar_count(
            session,
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.release_id == release_id,
                Issue.story_points.is_not(None),
                Issue.story_points >= 0,
            ),
        )
        completed_tickets = _scalar_count(
            session,
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.release_id == release_id,
                func.lower(Issue.status).in_(field_mapper.done_statuses),
            ),
        )
        changelog_entries = _scalar_count(
            session,
            select(func.count())
            .select_from(IssueHistory)
            .where(IssueHistory.issue_key.in_(release_issue_keys)),
        )
        context = MetricAvailabilityContext(
            has_tickets=total_tickets > 0,
            has_story_points=story_point_tickets > 0,
            has_completed_tickets=completed_tickets > 0,
            has_release_scope=total_tickets > 0,
            has_sprint_scope=False,
            has_changelog=changelog_entries > 0,
        )
        return MetricAvailability(
            context=context,
            metrics=_build_metric_availability_items(context, RELEASE_METRIC_DEPENDENCIES),
        )

    @staticmethod
    def build_sprint_availability(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> MetricAvailability:
        sprint_issue_keys = select(IssueSprint.issue_key).where(IssueSprint.sprint_id == sprint_id)
        total_tickets = _scalar_count(
            session,
            select(func.count()).select_from(IssueSprint).where(IssueSprint.sprint_id == sprint_id),
        )
        story_point_tickets = _scalar_count(
            session,
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.issue_key.in_(sprint_issue_keys),
                Issue.story_points.is_not(None),
                Issue.story_points >= 0,
            ),
        )
        completed_tickets = _scalar_count(
            session,
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.issue_key.in_(sprint_issue_keys),
                func.lower(Issue.status).in_(field_mapper.done_statuses),
            ),
        )
        changelog_entries = _scalar_count(
            session,
            select(func.count())
            .select_from(IssueHistory)
            .where(IssueHistory.issue_key.in_(sprint_issue_keys)),
        )
        context = MetricAvailabilityContext(
            has_tickets=total_tickets > 0,
            has_story_points=(
                total_tickets > 0 and 100.0 * story_point_tickets / total_tickets >= 50.0
            ),
            has_completed_tickets=completed_tickets > 0,
            has_release_scope=False,
            has_sprint_scope=total_tickets > 0,
            has_changelog=changelog_entries > 0,
        )
        return MetricAvailability(
            context=context,
            metrics=_build_metric_availability_items(context, SPRINT_METRIC_DEPENDENCIES),
        )

    @staticmethod
    def computation_state(
        availability: MetricAvailability,
        *,
        is_computed: bool,
        empty_scope_reason: str,
    ) -> tuple[str, str | None]:
        if not availability.context.has_tickets:
            return COMPUTATION_STATUS_NOT_COMPUTED, empty_scope_reason
        if not is_computed:
            return COMPUTATION_STATUS_NOT_COMPUTED, UNAVAILABLE_REASON_NOT_COMPUTED

        unavailable_reason = _first_metric_unavailable_reason(availability)
        if unavailable_reason is not None:
            return COMPUTATION_STATUS_PARTIAL, unavailable_reason
        return COMPUTATION_STATUS_COMPUTED, None


def _scalar_count(session: Session, query) -> int:
    return int(session.scalar(query) or 0)


def _build_metric_availability_items(
    context: MetricAvailabilityContext,
    dependencies_by_metric: dict[str, list[str]],
) -> dict[str, MetricAvailabilityItem]:
    return {
        metric_name: MetricAvailabilityItem(
            available=_dependencies_available(context, dependencies),
            reason=_first_unavailable_reason(context, dependencies),
            depends_on=dependencies,
        )
        for metric_name, dependencies in dependencies_by_metric.items()
    }


def _dependencies_available(context: MetricAvailabilityContext, dependencies: Iterable[str]) -> bool:
    return all(_dependency_available(context, dependency) for dependency in dependencies)


def _first_unavailable_reason(context: MetricAvailabilityContext, dependencies: Iterable[str]) -> str | None:
    for dependency in dependencies:
        if not _dependency_available(context, dependency):
            return _unavailable_reason(dependency)
    return None


def _first_metric_unavailable_reason(availability: MetricAvailability) -> str | None:
    if any(
        not item.available and item.reason == UNAVAILABLE_REASON_NO_STORY_POINTS
        for item in availability.metrics.values()
    ):
        return UNAVAILABLE_REASON_NO_STORY_POINTS
    for item in availability.metrics.values():
        if not item.available and item.reason:
            return item.reason
    return None


def _dependency_available(context: MetricAvailabilityContext, dependency: str) -> bool:
    if dependency == DEPENDENCY_TICKET_COUNT:
        return context.has_tickets
    if dependency == DEPENDENCY_STORY_POINTS:
        return context.has_story_points
    if dependency == DEPENDENCY_COMPLETED_TICKETS:
        return context.has_completed_tickets
    if dependency == DEPENDENCY_HISTORY_CHANGELOG:
        return context.has_changelog
    if dependency == DEPENDENCY_RELEASE_ASSIGNMENT:
        return context.has_release_scope
    if dependency == DEPENDENCY_SPRINT_ASSIGNMENT:
        return context.has_sprint_scope
    raise ValueError(f"Unknown metric dependency: {dependency}")


def _unavailable_reason(dependency: str) -> str:
    reasons = {
        DEPENDENCY_TICKET_COUNT: UNAVAILABLE_REASON_NO_TICKETS,
        DEPENDENCY_STORY_POINTS: UNAVAILABLE_REASON_NO_STORY_POINTS,
        DEPENDENCY_COMPLETED_TICKETS: "No completed tickets are available for this scope.",
        DEPENDENCY_HISTORY_CHANGELOG: UNAVAILABLE_REASON_NO_CHANGELOG,
        DEPENDENCY_RELEASE_ASSIGNMENT: UNAVAILABLE_REASON_NO_TICKETS,
        DEPENDENCY_SPRINT_ASSIGNMENT: UNAVAILABLE_REASON_NO_TICKETS,
    }
    return reasons[dependency]
