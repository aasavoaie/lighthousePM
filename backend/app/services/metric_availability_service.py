import math
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any, Final, Literal, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.metric_catalog import (
    RELEASE_METRICS,
    SPRINT_METRICS,
    metric_minimum_coverage_pct,
)
from app.models import Issue, IssueHistory, IssueSprint, Sprint
from app.schemas.availability import (
    MetricAvailability,
    MetricAvailabilityContext,
    MetricAvailabilityItem,
    MetricAvailabilityStatus,
)
from app.services.jira_field_mapper import JiraFieldMapper

ComputationStatus = Literal["COMPUTED", "PARTIAL", "NOT_COMPUTED"]

COMPUTATION_STATUS_COMPUTED: Final[Literal["COMPUTED"]] = "COMPUTED"
COMPUTATION_STATUS_PARTIAL: Final[Literal["PARTIAL"]] = "PARTIAL"
COMPUTATION_STATUS_NOT_COMPUTED: Final[Literal["NOT_COMPUTED"]] = "NOT_COMPUTED"
COMPUTATION_STATUS_NOT_APPLICABLE: Final[Literal["NOT_APPLICABLE"]] = (
    "NOT_APPLICABLE"
)
UNAVAILABLE_REASON_NO_TICKETS = "No tickets are available for this scope."
UNAVAILABLE_REASON_NO_STORY_POINTS = "Delivery confidence requires at least 50% of sprint tickets to have valid story points."
UNAVAILABLE_REASON_NO_CHANGELOG = (
    "No Jira changelog history is available for this scope."
)
UNAVAILABLE_REASON_RELEASE_EMPTY = UNAVAILABLE_REASON_NO_TICKETS
UNAVAILABLE_REASON_SPRINT_EMPTY = UNAVAILABLE_REASON_NO_TICKETS
UNAVAILABLE_REASON_NOT_COMPUTED = "Metrics have not been computed yet."
MIN_STORY_POINT_COVERAGE_PCT = metric_minimum_coverage_pct(
    "sprint.delivery_confidence_score"
)

DEPENDENCY_TICKET_COUNT = "ticket_count"
DEPENDENCY_TICKET_STATUS = "ticket_status"
DEPENDENCY_STORY_POINTS = "story_points"
DEPENDENCY_COMPLETED_TICKETS = "completed_tickets"
DEPENDENCY_HISTORY_CHANGELOG = "history_changelog"
DEPENDENCY_RELEASE_ASSIGNMENT = "release_assignment"
DEPENDENCY_SPRINT_ASSIGNMENT = "sprint_assignment"
DEPENDENCY_PROJECT_CHANGELOG_COMPLETENESS = "project_changelog_completeness"
DEPENDENCY_OBSERVED_RELEASE_SCOPE = "observed_release_scope"
DEPENDENCY_BLOCKER_CLASSIFICATION = "blocker_classification"
DEPENDENCY_SPRINT_DURATION = "sprint_duration"
DEPENDENCY_ASSIGNEE_IDENTITY = "assignee_identity"

RELEASE_METRIC_DEPENDENCIES: dict[str, list[str]] = {
    metric.api_field: list(metric.availability.dependencies)
    for metric in RELEASE_METRICS
}

SPRINT_METRIC_DEPENDENCIES: dict[str, list[str]] = {
    metric.api_field: list(metric.availability.dependencies)
    for metric in SPRINT_METRICS
}


class MetricAvailabilityService:
    """Build deterministic metric availability rules for API responses."""

    @staticmethod
    def build_release_availability(
        session: Session,
        release_id: str,
        field_mapper: JiraFieldMapper,
        scope_churn_result: dict[str, object] | None = None,
        flow_metric_results: dict[str, dict[str, object]] | None = None,
    ) -> MetricAvailability:
        release_issues = list(
            session.scalars(
                select(Issue)
                .where(Issue.release_id == release_id)
                .order_by(Issue.issue_key)
            ).all()
        )
        release_issue_keys = select(Issue.issue_key).where(
            Issue.release_id == release_id
        )
        total_tickets = _scalar_count(
            session,
            select(func.count())
            .select_from(Issue)
            .where(Issue.release_id == release_id),
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
        classification_results = _evaluate_classification_metrics(
            release_issues, field_mapper
        )
        metrics = _build_metric_availability_items(
            context,
            RELEASE_METRIC_DEPENDENCIES,
            classification_results=classification_results,
        )
        if scope_churn_result is not None:
            _apply_scope_churn_availability(metrics, scope_churn_result)
        if flow_metric_results is not None:
            _apply_flow_metric_availability(metrics, flow_metric_results)
        unavailable_confidence_metrics = [
            metric_name
            for metric_name in ("open_blockers", "open_high_severity_bugs")
            if classification_results[metric_name]["status"]
            == COMPUTATION_STATUS_PARTIAL
        ]
        result_by_metric: dict[str, dict[str, object]] = {
            metric_name: classification_results[metric_name]
            for metric_name in unavailable_confidence_metrics
        }
        if (
            scope_churn_result is not None
            and scope_churn_result["status"] == COMPUTATION_STATUS_PARTIAL
        ):
            unavailable_confidence_metrics.append("scope_churn_7d_pct")
            result_by_metric["scope_churn_7d_pct"] = scope_churn_result
        for metric_name, result in (flow_metric_results or {}).items():
            if result["status"] != COMPUTATION_STATUS_COMPUTED:
                unavailable_confidence_metrics.append(metric_name)
                result_by_metric[metric_name] = result
        if unavailable_confidence_metrics:
            unavailable_confidence_metrics = sorted(set(unavailable_confidence_metrics))
            missing_issue_keys = sorted(
                {
                    str(issue_key)
                    for metric_name in unavailable_confidence_metrics
                    for issue_key in cast(
                        Iterable[object],
                        result_by_metric[metric_name].get("missing_issue_keys", []),
                    )
                }
            )
            explanation = (
                "Release confidence is unavailable because required metric inputs are "
                f"unavailable for: {', '.join(unavailable_confidence_metrics)}."
            )
            status = (
                COMPUTATION_STATUS_PARTIAL
                if any(
                    result_by_metric[metric_name]["status"]
                    == COMPUTATION_STATUS_PARTIAL
                    for metric_name in unavailable_confidence_metrics
                )
                else COMPUTATION_STATUS_NOT_COMPUTED
            )
            metrics["confidence_score"] = MetricAvailabilityItem(
                status=status,
                available=False,
                reason=explanation,
                explanations=[explanation],
                missing_issue_keys=missing_issue_keys,
                depends_on=RELEASE_METRIC_DEPENDENCIES["confidence_score"],
            )

            unavailable_readiness_metrics = [
                metric_name
                for metric_name in unavailable_confidence_metrics
                if metric_name != "median_cycle_time_days"
                or result_by_metric[metric_name]["status"] == COMPUTATION_STATUS_PARTIAL
            ]
            if unavailable_readiness_metrics:
                readiness_missing_issue_keys = sorted(
                    {
                        str(issue_key)
                        for metric_name in unavailable_readiness_metrics
                        for issue_key in cast(
                            Iterable[object],
                            result_by_metric[metric_name].get(
                                "missing_issue_keys", []
                            ),
                        )
                    }
                )
                readiness_explanation = (
                    "Release readiness is unavailable because required gate inputs are "
                    f"unavailable for: {', '.join(unavailable_readiness_metrics)}."
                )
                readiness_status = (
                    COMPUTATION_STATUS_PARTIAL
                    if any(
                        result_by_metric[metric_name]["status"]
                        == COMPUTATION_STATUS_PARTIAL
                        for metric_name in unavailable_readiness_metrics
                    )
                    else COMPUTATION_STATUS_NOT_COMPUTED
                )
                for metric_name in ("gates_passed_count", "readiness_pct"):
                    metrics[metric_name] = MetricAvailabilityItem(
                        status=readiness_status,
                        available=False,
                        reason=readiness_explanation,
                        explanations=[readiness_explanation],
                        missing_issue_keys=readiness_missing_issue_keys,
                        depends_on=RELEASE_METRIC_DEPENDENCIES[metric_name],
                    )
        return MetricAvailability(context=context, metrics=metrics)

    @staticmethod
    def build_sprint_availability(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
        flow_metric_results: dict[str, dict[str, object]] | None = None,
        scope_metric_results: dict[str, dict[str, object]] | None = None,
        work_state_metric_results: dict[str, dict[str, object]] | None = None,
        scope_creep_result: dict[str, object] | None = None,
        delivery_confidence_result: dict[str, object] | None = None,
        workload_distribution_result: dict[str, object] | None = None,
    ) -> MetricAvailability:
        sprint_issue_keys = select(IssueSprint.issue_key).where(
            IssueSprint.sprint_id == sprint_id
        )
        sprint_issues = list(
            session.scalars(
                select(Issue)
                .where(Issue.issue_key.in_(sprint_issue_keys))
                .order_by(Issue.issue_key)
            ).all()
        )
        total_tickets = _scalar_count(
            session,
            select(func.count())
            .select_from(IssueSprint)
            .where(IssueSprint.sprint_id == sprint_id),
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
                total_tickets > 0
                and 100.0 * story_point_tickets / total_tickets
                >= MIN_STORY_POINT_COVERAGE_PCT
            ),
            has_completed_tickets=completed_tickets > 0,
            has_release_scope=False,
            has_sprint_scope=total_tickets > 0,
            has_changelog=changelog_entries > 0,
        )
        classification_results = _evaluate_classification_metrics(
            sprint_issues, field_mapper
        )
        metrics = _build_metric_availability_items(
            context,
            SPRINT_METRIC_DEPENDENCIES,
            classification_results={
                metric_name: classification_results[metric_name]
                for metric_name in ("open_blockers", "open_high_severity_bugs")
            },
        )
        _apply_sprint_scope_metric_availability(
            metrics,
            scope_metric_results
            or MetricAvailabilityService.evaluate_sprint_scope_metrics(
                session,
                sprint_id,
                field_mapper,
            ),
        )
        _apply_sprint_work_state_metric_availability(
            metrics,
            work_state_metric_results
            or MetricAvailabilityService.evaluate_sprint_work_state_metrics(
                session,
                sprint_id,
                field_mapper,
            ),
        )
        if scope_creep_result is not None:
            _apply_scope_creep_availability(metrics, scope_creep_result)
        if flow_metric_results is not None:
            _apply_flow_metric_availability(metrics, flow_metric_results)
        if workload_distribution_result is not None:
            _apply_workload_distribution_availability(
                metrics,
                workload_distribution_result,
            )
        prerequisites = (
            delivery_confidence_result.get("prerequisites")
            if delivery_confidence_result is not None
            else MetricAvailabilityService.evaluate_sprint_delivery_confidence_prerequisites(
                session=session,
                sprint_id=sprint_id,
                field_mapper=field_mapper,
                classification_results=classification_results,
            )
        )
        if context.has_story_points and prerequisites is not None:
            _apply_delivery_confidence_prerequisite_availability(
                metrics,
                cast(dict[str, object], prerequisites),
            )
        if context.has_story_points and delivery_confidence_result is not None:
            _apply_delivery_confidence_result_availability(
                metrics,
                delivery_confidence_result,
                scope_creep_result,
            )
        return MetricAvailability(context=context, metrics=metrics)

    @staticmethod
    def evaluate_release_classification_metrics(
        session: Session,
        release_id: str,
        field_mapper: JiraFieldMapper,
    ) -> dict[str, dict[str, Any]]:
        issues = list(
            session.scalars(
                select(Issue)
                .where(Issue.release_id == release_id)
                .order_by(Issue.issue_key)
            ).all()
        )
        return _evaluate_classification_metrics(issues, field_mapper)

    @staticmethod
    def evaluate_sprint_classification_metrics(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> dict[str, dict[str, Any]]:
        issue_keys = select(IssueSprint.issue_key).where(
            IssueSprint.sprint_id == sprint_id
        )
        issues = list(
            session.scalars(
                select(Issue)
                .where(Issue.issue_key.in_(issue_keys))
                .order_by(Issue.issue_key)
            ).all()
        )
        results = _evaluate_classification_metrics(issues, field_mapper)
        return {
            metric_name: results[metric_name]
            for metric_name in ("open_blockers", "open_high_severity_bugs")
        }

    @staticmethod
    def evaluate_sprint_delivery_confidence_prerequisites(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
        classification_results: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Evaluate every required non-point input for delivery confidence."""
        sprint = session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))
        if sprint is None:
            raise ValueError(f"Sprint not found: {sprint_id!r}")

        sprint_issue_keys = select(IssueSprint.issue_key).where(
            IssueSprint.sprint_id == sprint_id
        )
        sprint_issues = list(
            session.scalars(
                select(Issue)
                .where(Issue.issue_key.in_(sprint_issue_keys))
                .order_by(Issue.issue_key)
            ).all()
        )
        pointed_missing_status_issue_keys = sorted(
            issue.issue_key
            for issue in sprint_issues
            if _has_valid_story_points(issue.story_points)
            and not _has_text(issue.status)
        )

        evaluated_classification = (
            classification_results
            or _evaluate_classification_metrics(
                sprint_issues,
                field_mapper,
            )
        )
        blocker_missing_issue_keys = sorted(
            str(key)
            for key in evaluated_classification["open_blockers"].get(
                "missing_issue_keys", []
            )
        )

        start_at = _coerce_utc(sprint.start_date)
        end_at = _coerce_utc(sprint.end_date)
        duration_valid = (
            start_at is not None and end_at is not None and end_at > start_at
        )
        duration_reason: str | None = None
        if start_at is None and end_at is None:
            duration_reason = (
                "Delivery confidence is inconclusive because sprint duration requires both "
                "a start time and an end time."
            )
        elif start_at is None:
            duration_reason = "Delivery confidence is inconclusive because sprint duration is missing its start time."
        elif end_at is None:
            duration_reason = "Delivery confidence is inconclusive because sprint duration is missing its end time."
        elif end_at <= start_at:
            duration_reason = (
                "Delivery confidence is inconclusive because sprint duration is invalid: "
                "the end time must be later than the start time."
            )

        project_prefix = f"{sprint.project_key.strip().casefold()}-"
        project_issues = list(
            session.scalars(select(Issue).order_by(Issue.issue_key)).all()
        )
        project_issue_keys = sorted(
            issue.issue_key
            for issue in project_issues
            if issue.issue_key.casefold().startswith(project_prefix)
        )
        incomplete_project_history_issue_keys = sorted(
            issue.issue_key
            for issue in project_issues
            if issue.issue_key.casefold().startswith(project_prefix)
            and not issue.jira_changelog_complete
        )

        explanations: list[str] = []
        if pointed_missing_status_issue_keys:
            explanations.append(
                "Delivery confidence is inconclusive because pointed current-sprint tickets "
                "are missing status: "
                + ", ".join(pointed_missing_status_issue_keys)
                + "."
            )
        if blocker_missing_issue_keys:
            explanations.append(
                "Delivery confidence is inconclusive because blocker classification is incomplete "
                "for current-sprint tickets: "
                + ", ".join(blocker_missing_issue_keys)
                + "."
            )
        if duration_reason is not None:
            explanations.append(duration_reason)
        if incomplete_project_history_issue_keys:
            explanations.append(
                "Delivery confidence is inconclusive because sprint-membership changelog history "
                "is incomplete for synchronized project tickets: "
                + ", ".join(incomplete_project_history_issue_keys)
                + "."
            )

        missing_issue_keys = sorted(
            set(pointed_missing_status_issue_keys)
            | set(blocker_missing_issue_keys)
            | set(incomplete_project_history_issue_keys)
        )
        return {
            "status": (
                COMPUTATION_STATUS_COMPUTED
                if not explanations
                else COMPUTATION_STATUS_NOT_COMPUTED
            ),
            "available": not explanations,
            "explanations": explanations,
            "missing_issue_keys": missing_issue_keys,
            "evidence": {
                "pointed_missing_status_issue_keys": pointed_missing_status_issue_keys,
                "incomplete_blocker_classification_issue_keys": blocker_missing_issue_keys,
                "sprint_start_at": start_at.isoformat()
                if start_at is not None
                else None,
                "sprint_end_at": end_at.isoformat() if end_at is not None else None,
                "sprint_duration_valid": duration_valid,
                "project_issue_keys": project_issue_keys,
                "incomplete_project_sprint_history_issue_keys": (
                    incomplete_project_history_issue_keys
                ),
            },
        }

    @staticmethod
    def evaluate_sprint_scope_metrics(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> dict[str, dict[str, Any]]:
        current_scope_issue_keys = sorted(
            set(
                session.scalars(
                    select(IssueSprint.issue_key).where(
                        IssueSprint.sprint_id == sprint_id
                    )
                ).all()
            )
        )
        issues = list(
            session.scalars(
                select(Issue)
                .where(Issue.issue_key.in_(current_scope_issue_keys))
                .order_by(Issue.issue_key)
            ).all()
        )
        completed_scope = _evaluate_classification_metrics(issues, field_mapper)[
            "scope_completed_pct"
        ]
        if completed_scope["status"] == COMPUTATION_STATUS_PARTIAL:
            missing_count = len(completed_scope["missing_issue_keys"])
            completed_scope["explanations"] = [
                "Completed scope is unavailable because "
                f"{missing_count} current sprint ticket(s) have no status."
            ]
        completed_scope["evidence"] = {
            **completed_scope["evidence"],
            "current_scope_issue_keys": current_scope_issue_keys,
            "current_scope_count": len(current_scope_issue_keys),
            "completed_issue_keys": list(
                completed_scope["evidence"].get("matching_issue_keys", [])
            ),
        }

        has_scope = bool(current_scope_issue_keys)
        return {
            "committed_scope": {
                "value": len(current_scope_issue_keys) if has_scope else None,
                "status": (
                    COMPUTATION_STATUS_COMPUTED
                    if has_scope
                    else COMPUTATION_STATUS_NOT_COMPUTED
                ),
                "available": has_scope,
                "explanations": [] if has_scope else [UNAVAILABLE_REASON_NO_TICKETS],
                "missing_issue_keys": [],
                "evidence": {
                    "current_scope_issue_keys": current_scope_issue_keys,
                    "current_scope_count": len(current_scope_issue_keys),
                },
            },
            "completed_scope_pct": completed_scope,
        }

    @staticmethod
    def evaluate_sprint_work_state_metrics(
        session: Session,
        sprint_id: str,
        field_mapper: JiraFieldMapper,
    ) -> dict[str, dict[str, Any]]:
        sprint = session.scalar(select(Sprint).where(Sprint.sprint_id == sprint_id))
        if sprint is None:
            raise ValueError(f"Sprint not found: {sprint_id!r}")

        current_scope_issue_keys = sorted(
            set(
                session.scalars(
                    select(IssueSprint.issue_key).where(
                        IssueSprint.sprint_id == sprint_id
                    )
                ).all()
            )
        )
        issues = list(
            session.scalars(
                select(Issue)
                .where(Issue.issue_key.in_(current_scope_issue_keys))
                .order_by(Issue.issue_key)
            ).all()
        )
        missing_status_issue_keys = sorted(
            issue.issue_key for issue in issues if not _has_text(issue.status)
        )
        in_progress_issue_keys = sorted(
            issue.issue_key
            for issue in issues
            if _has_text(issue.status)
            and field_mapper.is_in_progress_status(issue.status)
        )
        not_started_issue_keys = sorted(
            issue.issue_key
            for issue in issues
            if _has_text(issue.status)
            and not field_mapper.is_done_status(issue.status)
            and not field_mapper.is_in_progress_status(issue.status)
        )
        unfinished_issue_keys = sorted(
            issue.issue_key
            for issue in issues
            if _has_text(issue.status) and not field_mapper.is_done_status(issue.status)
        )
        has_scope = bool(current_scope_issue_keys)
        is_partial = bool(missing_status_issue_keys)
        sprint_state = sprint.state.strip().casefold()
        common_evidence = {
            "current_scope_issue_keys": current_scope_issue_keys,
            "current_scope_count": len(current_scope_issue_keys),
            "missing_status_issue_keys": missing_status_issue_keys,
        }

        def count_result(
            metric_label: str,
            matching_issue_keys: list[str],
        ) -> dict[str, Any]:
            if not has_scope:
                return {
                    "value": None,
                    "status": COMPUTATION_STATUS_NOT_COMPUTED,
                    "available": False,
                    "explanations": [UNAVAILABLE_REASON_NO_TICKETS],
                    "missing_issue_keys": [],
                    "evidence": {
                        **common_evidence,
                        "matching_issue_keys": [],
                    },
                }
            explanations = (
                [
                    f"{metric_label} is partial because "
                    f"{len(missing_status_issue_keys)} current sprint ticket(s) have no status. "
                    "The returned value is a confirmed minimum."
                ]
                if is_partial
                else []
            )
            return {
                "value": len(matching_issue_keys),
                "status": (
                    COMPUTATION_STATUS_PARTIAL
                    if is_partial
                    else COMPUTATION_STATUS_COMPUTED
                ),
                "available": True,
                "explanations": explanations,
                "missing_issue_keys": missing_status_issue_keys,
                "evidence": {
                    **common_evidence,
                    "matching_issue_keys": matching_issue_keys,
                },
            }

        in_progress = count_result("In-progress count", in_progress_issue_keys)
        not_started = count_result("Not-started count", not_started_issue_keys)

        rollover_evidence = {
            **common_evidence,
            "sprint_state": sprint_state,
            "applicable": sprint_state == "closed",
            "unfinished_issue_keys": unfinished_issue_keys,
        }
        if sprint_state != "closed":
            rollover: dict[str, Any] = {
                "value": None,
                "status": COMPUTATION_STATUS_NOT_APPLICABLE,
                "available": False,
                "explanations": [
                    "Unfinished closed-sprint scope applies only to closed sprints."
                ],
                "missing_issue_keys": [],
                "evidence": rollover_evidence,
            }
        elif not has_scope:
            rollover = {
                "value": None,
                "status": COMPUTATION_STATUS_NOT_COMPUTED,
                "available": False,
                "explanations": [UNAVAILABLE_REASON_NO_TICKETS],
                "missing_issue_keys": [],
                "evidence": rollover_evidence,
            }
        else:
            rollover = {
                "value": len(unfinished_issue_keys),
                "status": (
                    COMPUTATION_STATUS_PARTIAL
                    if is_partial
                    else COMPUTATION_STATUS_COMPUTED
                ),
                "available": True,
                "explanations": (
                    [
                        "Unfinished closed-sprint scope is partial because "
                        f"{len(missing_status_issue_keys)} current sprint ticket(s) have no status. "
                        "The returned value is a confirmed minimum."
                    ]
                    if is_partial
                    else []
                ),
                "missing_issue_keys": missing_status_issue_keys,
                "evidence": rollover_evidence,
            }

        return {
            "in_progress_count": in_progress,
            "not_started_count": not_started,
            "rollover_count": rollover,
        }

    @staticmethod
    def computation_state(
        availability: MetricAvailability,
        *,
        is_computed: bool,
        empty_scope_reason: str,
    ) -> tuple[ComputationStatus, str | None]:
        if not availability.context.has_tickets:
            return COMPUTATION_STATUS_NOT_COMPUTED, empty_scope_reason
        if not is_computed:
            return COMPUTATION_STATUS_NOT_COMPUTED, UNAVAILABLE_REASON_NOT_COMPUTED

        unavailable_reason = _first_metric_unavailable_reason(availability)
        if unavailable_reason is not None:
            return COMPUTATION_STATUS_PARTIAL, unavailable_reason
        return COMPUTATION_STATUS_COMPUTED, None


def _evaluate_classification_metrics(
    issues: Sequence[Issue],
    field_mapper: JiraFieldMapper,
) -> dict[str, dict[str, Any]]:
    issue_keys = [issue.issue_key for issue in issues]
    if not issues:
        empty_evidence: dict[str, list[str]] = {
            "evaluated_issue_keys": [],
            "matching_issue_keys": [],
        }
        return {
            metric_name: {
                "value": None,
                "status": COMPUTATION_STATUS_NOT_COMPUTED,
                "available": False,
                "explanations": [UNAVAILABLE_REASON_NO_TICKETS],
                "missing_issue_keys": [],
                "evidence": dict(empty_evidence),
            }
            for metric_name in (
                "open_blockers",
                "open_high_severity_bugs",
                "scope_completed_pct",
                "completed_tickets",
            )
        }

    blocker_matching: list[str] = []
    blocker_evaluated: list[str] = []
    blocker_missing_status: list[str] = []
    blocker_missing_type: list[str] = []
    blocker_missing_severity: list[str] = []
    blocker_indeterminate: list[str] = []

    high_bug_matching: list[str] = []
    high_bug_evaluated: list[str] = []
    high_bug_missing_status: list[str] = []
    high_bug_missing_type: list[str] = []
    high_bug_missing_severity: list[str] = []

    status_evaluated: list[str] = []
    completed_matching: list[str] = []
    missing_status: list[str] = []

    for issue in issues:
        key = issue.issue_key
        has_status = _has_text(issue.status)
        has_issue_type = _has_text(issue.issue_type)
        has_severity = _has_text(issue.priority)

        if has_status:
            status_evaluated.append(key)
            if field_mapper.is_done_status(issue.status):
                completed_matching.append(key)
        else:
            missing_status.append(key)

        if not has_status:
            blocker_missing_status.append(key)
            blocker_indeterminate.append(key)
        elif issue.jira_blocker_flag is not None:
            blocker_evaluated.append(key)
            if field_mapper.classify_blocker(
                issue_type=issue.issue_type,
                severity=issue.priority,
                status=issue.status,
                blocker_flag=issue.jira_blocker_flag,
            ):
                blocker_matching.append(key)
        elif field_mapper.is_done_status(issue.status):
            blocker_evaluated.append(key)
        else:
            known_fallback_match = field_mapper.classify_blocker(
                issue_type=issue.issue_type,
                severity=issue.priority,
                status=issue.status,
                blocker_flag=None,
            )
            missing_type = bool(field_mapper.blocker_issue_types) and not has_issue_type
            missing_severity = (
                bool(field_mapper.blocker_severity_values) and not has_severity
            )
            if known_fallback_match:
                blocker_evaluated.append(key)
                blocker_matching.append(key)
            elif missing_type or missing_severity:
                if missing_type:
                    blocker_missing_type.append(key)
                if missing_severity:
                    blocker_missing_severity.append(key)
                blocker_indeterminate.append(key)
            else:
                blocker_evaluated.append(key)

        if not has_issue_type:
            high_bug_missing_type.append(key)
        elif not field_mapper.is_bug(issue.issue_type):
            high_bug_evaluated.append(key)
        elif not has_severity:
            high_bug_missing_severity.append(key)
        elif not field_mapper.is_high_severity(issue.priority):
            high_bug_evaluated.append(key)
        elif not has_status:
            high_bug_missing_status.append(key)
        else:
            high_bug_evaluated.append(key)
            if not field_mapper.is_done_status(issue.status):
                high_bug_matching.append(key)

    blocker_missing = sorted(set(blocker_indeterminate))
    blocker_partial = bool(blocker_missing)
    high_bug_missing = sorted(
        set(high_bug_missing_type + high_bug_missing_severity + high_bug_missing_status)
    )
    high_bug_partial = bool(high_bug_missing)
    status_partial = bool(missing_status)

    blocker_explanations = (
        [
            "Open blockers are a confirmed minimum because blocker classification is "
            f"incomplete for {len(blocker_missing)} ticket(s). Additional blockers may exist."
        ]
        if blocker_partial
        else []
    )
    high_bug_explanations = (
        [
            "Open high-severity bugs are a confirmed minimum because classification is "
            f"incomplete for {len(high_bug_missing)} ticket(s). Additional high-severity bugs may exist."
        ]
        if high_bug_partial
        else []
    )
    scope_explanations = (
        [
            "Scope completed is unavailable because "
            f"{len(missing_status)} ticket(s) have no status."
        ]
        if status_partial
        else []
    )
    completed_explanations = (
        [
            "Completed tickets are a confirmed minimum because "
            f"{len(missing_status)} ticket(s) have no status. Additional completed tickets may exist."
        ]
        if status_partial
        else []
    )

    return {
        "open_blockers": {
            "value": len(blocker_matching),
            "status": COMPUTATION_STATUS_PARTIAL
            if blocker_partial
            else COMPUTATION_STATUS_COMPUTED,
            "available": True,
            "explanations": blocker_explanations,
            "missing_issue_keys": blocker_missing,
            "evidence": {
                "evaluated_issue_keys": blocker_evaluated,
                "matching_issue_keys": blocker_matching,
                "missing_status_issue_keys": blocker_missing_status,
                "missing_issue_type_issue_keys": blocker_missing_type,
                "missing_severity_issue_keys": blocker_missing_severity,
                "indeterminate_blocker_issue_keys": blocker_indeterminate,
            },
        },
        "open_high_severity_bugs": {
            "value": len(high_bug_matching),
            "status": COMPUTATION_STATUS_PARTIAL
            if high_bug_partial
            else COMPUTATION_STATUS_COMPUTED,
            "available": True,
            "explanations": high_bug_explanations,
            "missing_issue_keys": high_bug_missing,
            "evidence": {
                "evaluated_issue_keys": high_bug_evaluated,
                "matching_issue_keys": high_bug_matching,
                "missing_status_issue_keys": high_bug_missing_status,
                "missing_issue_type_issue_keys": high_bug_missing_type,
                "missing_severity_issue_keys": high_bug_missing_severity,
            },
        },
        "scope_completed_pct": {
            "value": (
                None
                if status_partial
                else round(100.0 * len(completed_matching) / len(issue_keys), 2)
            ),
            "status": COMPUTATION_STATUS_PARTIAL
            if status_partial
            else COMPUTATION_STATUS_COMPUTED,
            "available": not status_partial,
            "explanations": scope_explanations,
            "missing_issue_keys": list(missing_status),
            "evidence": {
                "evaluated_issue_keys": status_evaluated,
                "matching_issue_keys": completed_matching,
                "missing_status_issue_keys": missing_status,
            },
        },
        "completed_tickets": {
            "value": len(completed_matching),
            "status": COMPUTATION_STATUS_PARTIAL
            if status_partial
            else COMPUTATION_STATUS_COMPUTED,
            "available": True,
            "explanations": completed_explanations,
            "missing_issue_keys": list(missing_status),
            "evidence": {
                "evaluated_issue_keys": status_evaluated,
                "matching_issue_keys": completed_matching,
                "missing_status_issue_keys": missing_status,
            },
        },
    }


def _has_text(value: str | None) -> bool:
    return bool(value and value.strip())


def _has_valid_story_points(value: float | None) -> bool:
    return value is not None and math.isfinite(float(value)) and float(value) >= 0


def _coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _scalar_count(session: Session, query) -> int:
    return int(session.scalar(query) or 0)


def _build_metric_availability_items(
    context: MetricAvailabilityContext,
    dependencies_by_metric: dict[str, list[str]],
    *,
    classification_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, MetricAvailabilityItem]:
    items: dict[str, MetricAvailabilityItem] = {}
    for metric_name, dependencies in dependencies_by_metric.items():
        available = _dependencies_available(context, dependencies)
        unavailable_reason = _first_unavailable_reason(context, dependencies)
        items[metric_name] = MetricAvailabilityItem(
            status=(
                COMPUTATION_STATUS_COMPUTED
                if available
                else COMPUTATION_STATUS_NOT_COMPUTED
            ),
            available=available,
            reason=unavailable_reason,
            explanations=[unavailable_reason] if unavailable_reason else [],
            missing_issue_keys=[],
            depends_on=dependencies,
        )
    for metric_name, result in (classification_results or {}).items():
        explanations = list(result["explanations"])
        items[metric_name] = MetricAvailabilityItem(
            status=result["status"],
            available=bool(result["available"]),
            reason=explanations[0] if explanations else None,
            explanations=explanations,
            missing_issue_keys=list(result["missing_issue_keys"]),
            depends_on=dependencies_by_metric[metric_name],
        )
    return items


def _apply_scope_churn_availability(
    items: dict[str, MetricAvailabilityItem],
    result: dict[str, object],
) -> None:
    status = cast(MetricAvailabilityStatus, result["status"])
    explanations = [
        str(item)
        for item in cast(Iterable[object], result.get("explanations", []))
    ]
    missing_issue_keys = sorted(
        str(key)
        for key in cast(Iterable[object], result.get("missing_issue_keys", []))
    )
    for metric_name in (
        "scope_churn_7d_pct",
        "scope_added_7d_count",
        "scope_removed_7d_count",
    ):
        available = status == COMPUTATION_STATUS_COMPUTED or (
            status == COMPUTATION_STATUS_PARTIAL and metric_name != "scope_churn_7d_pct"
        )
        items[metric_name] = MetricAvailabilityItem(
            status=status,
            available=available,
            reason=explanations[0] if explanations else None,
            explanations=explanations,
            missing_issue_keys=missing_issue_keys,
            depends_on=[
                DEPENDENCY_PROJECT_CHANGELOG_COMPLETENESS,
                DEPENDENCY_OBSERVED_RELEASE_SCOPE,
            ],
        )


def _apply_flow_metric_availability(
    items: dict[str, MetricAvailabilityItem],
    results: dict[str, dict[str, object]],
) -> None:
    for metric_name in ("median_cycle_time_days", "reopen_rate_pct"):
        result = results[metric_name]
        status = cast(MetricAvailabilityStatus, result["status"])
        available = status == COMPUTATION_STATUS_COMPUTED
        explanations = [
            str(item)
            for item in cast(Iterable[object], result.get("explanations", []))
        ]
        items[metric_name] = MetricAvailabilityItem(
            status=status,
            available=available,
            reason=explanations[0] if not available and explanations else None,
            explanations=explanations,
            missing_issue_keys=sorted(
                str(key)
                for key in cast(
                    Iterable[object], result.get("missing_issue_keys", [])
                )
            ),
            depends_on=items[metric_name].depends_on,
        )


def _apply_sprint_scope_metric_availability(
    items: dict[str, MetricAvailabilityItem],
    results: dict[str, dict[str, object]],
) -> None:
    for metric_name in ("committed_scope", "completed_scope_pct"):
        result = results[metric_name]
        explanations = [
            str(item)
            for item in cast(Iterable[object], result.get("explanations", []))
        ]
        available = bool(result["available"])
        items[metric_name] = MetricAvailabilityItem(
            status=cast(MetricAvailabilityStatus, result["status"]),
            available=available,
            reason=explanations[0] if not available and explanations else None,
            explanations=explanations,
            missing_issue_keys=sorted(
                str(key)
                for key in cast(
                    Iterable[object], result.get("missing_issue_keys", [])
                )
            ),
            depends_on=items[metric_name].depends_on,
        )


def _apply_sprint_work_state_metric_availability(
    items: dict[str, MetricAvailabilityItem],
    results: dict[str, dict[str, object]],
) -> None:
    for metric_name in ("in_progress_count", "not_started_count", "rollover_count"):
        result = results[metric_name]
        explanations = [
            str(item)
            for item in cast(Iterable[object], result.get("explanations", []))
        ]
        available = bool(result["available"])
        items[metric_name] = MetricAvailabilityItem(
            status=cast(MetricAvailabilityStatus, result["status"]),
            available=available,
            reason=explanations[0] if not available and explanations else None,
            explanations=explanations,
            missing_issue_keys=sorted(
                str(key)
                for key in cast(
                    Iterable[object], result.get("missing_issue_keys", [])
                )
            ),
            depends_on=items[metric_name].depends_on,
        )


def _apply_scope_creep_availability(
    items: dict[str, MetricAvailabilityItem],
    result: dict[str, object],
) -> None:
    explanations = [
        str(item)
        for item in cast(Iterable[object], result.get("explanations", []))
    ]
    status = cast(MetricAvailabilityStatus, result["status"])
    available = status == COMPUTATION_STATUS_COMPUTED
    items["scope_creep_pct"] = MetricAvailabilityItem(
        status=status,
        available=available,
        reason=explanations[0] if not available and explanations else None,
        explanations=explanations,
        missing_issue_keys=sorted(
            str(key)
            for key in cast(
                Iterable[object], result.get("missing_issue_keys", [])
            )
        ),
        depends_on=SPRINT_METRIC_DEPENDENCIES["scope_creep_pct"],
    )


def _apply_delivery_confidence_prerequisite_availability(
    items: dict[str, MetricAvailabilityItem],
    result: dict[str, object],
) -> None:
    if bool(result["available"]):
        return
    explanations = [
        str(item)
        for item in cast(Iterable[object], result.get("explanations", []))
    ]
    items["delivery_confidence_score"] = MetricAvailabilityItem(
        status=COMPUTATION_STATUS_NOT_COMPUTED,
        available=False,
        reason=explanations[0] if explanations else None,
        explanations=explanations,
        missing_issue_keys=sorted(
            str(key)
            for key in cast(Iterable[object], result.get("missing_issue_keys", []))
        ),
        depends_on=SPRINT_METRIC_DEPENDENCIES["delivery_confidence_score"],
    )


def _apply_delivery_confidence_result_availability(
    items: dict[str, MetricAvailabilityItem],
    result: dict[str, object],
    scope_creep_result: dict[str, object] | None,
) -> None:
    if result.get("status") != "INCONCLUSIVE":
        return
    explanations = [
        str(item)
        for item in cast(Iterable[object], result.get("explanations", []))
    ]
    missing_issue_keys = sorted(
        {
            str(key)
            for key in (
                list(items["delivery_confidence_score"].missing_issue_keys)
                + list(
                    cast(
                        Iterable[object],
                        (scope_creep_result or {}).get("missing_issue_keys", []),
                    )
                )
            )
        }
    )
    items["delivery_confidence_score"] = MetricAvailabilityItem(
        status=COMPUTATION_STATUS_NOT_COMPUTED,
        available=False,
        reason=explanations[0] if explanations else None,
        explanations=explanations,
        missing_issue_keys=missing_issue_keys,
        depends_on=SPRINT_METRIC_DEPENDENCIES["delivery_confidence_score"],
    )


def _apply_workload_distribution_availability(
    items: dict[str, MetricAvailabilityItem],
    result: dict[str, object],
) -> None:
    result_status = str(result["status"])
    status = (
        COMPUTATION_STATUS_NOT_COMPUTED
        if result_status == "INCONCLUSIVE"
        else result_status
    )
    available = result_status in {
        COMPUTATION_STATUS_COMPUTED,
        COMPUTATION_STATUS_PARTIAL,
    }
    explanations = [
        str(item)
        for item in cast(Iterable[object], result.get("explanations", []))
    ]
    items["workload_concentration_pct"] = MetricAvailabilityItem(
        status=cast(MetricAvailabilityStatus, status),
        available=available,
        reason=explanations[0] if not available and explanations else None,
        explanations=explanations,
        missing_issue_keys=sorted(
            str(key)
            for key in cast(Iterable[object], result.get("missing_issue_keys", []))
        ),
        depends_on=SPRINT_METRIC_DEPENDENCIES["workload_concentration_pct"],
    )


def _dependencies_available(
    context: MetricAvailabilityContext, dependencies: Iterable[str]
) -> bool:
    return all(
        _dependency_available(context, dependency) for dependency in dependencies
    )


def _first_unavailable_reason(
    context: MetricAvailabilityContext, dependencies: Iterable[str]
) -> str | None:
    for dependency in dependencies:
        if not _dependency_available(context, dependency):
            return _unavailable_reason(dependency)
    return None


def _first_metric_unavailable_reason(availability: MetricAvailability) -> str | None:
    for item in availability.metrics.values():
        if item.status == COMPUTATION_STATUS_PARTIAL and item.explanations:
            return item.explanations[0]
    if any(
        not item.available and item.reason == UNAVAILABLE_REASON_NO_STORY_POINTS
        for item in availability.metrics.values()
    ):
        return UNAVAILABLE_REASON_NO_STORY_POINTS
    for item in availability.metrics.values():
        if (
            item.status != COMPUTATION_STATUS_NOT_APPLICABLE
            and not item.available
            and item.reason
        ):
            return item.reason
    return None


def _dependency_available(context: MetricAvailabilityContext, dependency: str) -> bool:
    if dependency == DEPENDENCY_TICKET_COUNT:
        return context.has_tickets
    if dependency == DEPENDENCY_TICKET_STATUS:
        # Metric-specific evaluators determine complete versus partial status evidence.
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
    if dependency in {
        DEPENDENCY_BLOCKER_CLASSIFICATION,
        DEPENDENCY_SPRINT_DURATION,
        DEPENDENCY_PROJECT_CHANGELOG_COMPLETENESS,
        DEPENDENCY_ASSIGNEE_IDENTITY,
    }:
        # Dedicated evaluators provide availability and exact evidence.
        return True
    raise ValueError(f"Unknown metric dependency: {dependency}")


def _unavailable_reason(dependency: str) -> str:
    reasons = {
        DEPENDENCY_TICKET_COUNT: UNAVAILABLE_REASON_NO_TICKETS,
        DEPENDENCY_TICKET_STATUS: UNAVAILABLE_REASON_NO_TICKETS,
        DEPENDENCY_STORY_POINTS: UNAVAILABLE_REASON_NO_STORY_POINTS,
        DEPENDENCY_COMPLETED_TICKETS: "No completed tickets are available for this scope.",
        DEPENDENCY_HISTORY_CHANGELOG: UNAVAILABLE_REASON_NO_CHANGELOG,
        DEPENDENCY_RELEASE_ASSIGNMENT: UNAVAILABLE_REASON_NO_TICKETS,
        DEPENDENCY_SPRINT_ASSIGNMENT: UNAVAILABLE_REASON_NO_TICKETS,
        DEPENDENCY_BLOCKER_CLASSIFICATION: "Blocker classification is incomplete.",
        DEPENDENCY_SPRINT_DURATION: "Sprint duration is missing or invalid.",
        DEPENDENCY_PROJECT_CHANGELOG_COMPLETENESS: (
            "Project sprint-membership changelog history is incomplete."
        ),
        DEPENDENCY_ASSIGNEE_IDENTITY: "Assignee identity evidence is incomplete.",
    }
    return reasons[dependency]
