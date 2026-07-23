from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy.orm import Session

from app.config import get_settings
from app.metric_catalog import metric_api_fields
from app.repositories.metric_repository import MetricRepository
from app.repositories.release_repository import ReleaseRepository
from app.schemas.metrics import (
    ChartPoint,
    ComputationStatus,
    MetricIssueKeys,
    MetricSeries,
    MetricThresholds,
    MetricValues,
    ReleaseChartsResponse,
    ReleaseMetricsResponse,
)
from app.schemas.deltas import (
    SnapshotBaseline,
    SnapshotChangeHistoryItem,
    SnapshotChangeHistoryResponse,
    SnapshotComparisonResponse,
    SnapshotDeltaComparison,
)
from app.services.application_errors import (
    ApplicationNotFoundError,
    ApplicationValidationError,
)
from app.services.jira_field_mapper import JiraFieldMapper
from app.services.metric_availability_service import (
    MetricAvailabilityService,
    UNAVAILABLE_REASON_RELEASE_EMPTY,
)
from app.services.recommendation_engine import RecommendationEngine
from app.services.snapshot_comparison_service import SnapshotComparisonService


RELEASE_METRIC_NAMES = list(metric_api_fields("release", api_location="metric_values"))
RELEASE_CHART_METRIC_NAMES = list(
    metric_api_fields("release", chart_participation=True)
)
RULESET_MISMATCH_REASON = (
    "Snapshot comparison unavailable because ruleset versions differ."
)
LEGACY_RELEASE_CONFIDENCE_REASON = "Derived legacy release confidence is unavailable because it was not stored at calculation time."
INCONCLUSIVE_RELEASE_CONFIDENCE_REASON = "Snapshot comparison unavailable because release confidence is inconclusive for one or both snapshots."
UNAVAILABLE_RELEASE_CONFIDENCE_REASON = "Snapshot comparison unavailable because release confidence is unavailable for one or both snapshots."


def _stored_metric_value(snapshot, metric_name: str, value):
    availability = (snapshot.calculation_provenance or {}).get("availability", {})
    metrics = availability.get("metrics", {}) if isinstance(availability, dict) else {}
    item = metrics.get(metric_name, {}) if isinstance(metrics, dict) else {}
    if isinstance(item, dict) and item.get("available") is False:
        return None
    return value


def _build_release_gate_values(snapshot) -> tuple[int | None, int, float | None]:
    outputs = (snapshot.calculation_provenance or {}).get("component_outputs", {})
    gates = outputs.get("release_gates", []) if isinstance(outputs, dict) else []
    if snapshot.ruleset_version == 0 or not isinstance(gates, list):
        return None, 0, None
    total = len(gates)
    passed = sum(
        1 for gate in gates if isinstance(gate, dict) and gate.get("passed") is True
    )
    readiness_pct = outputs.get("readiness_pct") if isinstance(outputs, dict) else None
    return passed, total, readiness_pct


def _empty_snapshot_comparison(
    entity_id: str,
    baseline: SnapshotBaseline,
    current_snapshot_at,
) -> SnapshotComparisonResponse:
    return SnapshotComparisonResponse(
        entity_id=entity_id,
        baseline=baseline,
        current_snapshot_at=current_snapshot_at,
        baseline_snapshot_at=None,
        has_baseline=False,
        current_ruleset_version=None,
        baseline_ruleset_version=None,
        unavailable_reason=None,
        comparison=SnapshotDeltaComparison(confidence_delta=0.0, contributors=[]),
    )


def _select_release_baseline_snapshot(
    session: Session,
    release_id: str,
    current_snapshot,
    baseline: SnapshotBaseline,
):
    if baseline == "previous":
        return MetricRepository.get_previous_snapshot(
            session=session,
            release_id=release_id,
            snapshot_at=current_snapshot.snapshot_at,
            snapshot_id=current_snapshot.id,
        )
    hours = 24 if baseline == "24h" else 24 * 7
    snapshot_at = current_snapshot.snapshot_at
    if snapshot_at.tzinfo is None:
        snapshot_at = snapshot_at.replace(tzinfo=UTC)
    else:
        snapshot_at = snapshot_at.astimezone(UTC)
    return MetricRepository.get_latest_snapshot_at_or_before(
        session=session,
        release_id=release_id,
        snapshot_at=snapshot_at - timedelta(hours=hours),
    )


def _build_release_history_items(snapshots) -> list[SnapshotChangeHistoryItem]:
    items: list[SnapshotChangeHistoryItem] = []
    previous_snapshot = None
    for snapshot in snapshots:
        confidence = snapshot.confidence_score if snapshot.ruleset_version > 0 else None
        version_boundary = (
            previous_snapshot is not None
            and previous_snapshot.ruleset_version != snapshot.ruleset_version
        )
        classification_reason = (
            SnapshotComparisonService.classification_unavailable_reason(
                snapshot,
                previous_snapshot,
            )
            if previous_snapshot is not None and not version_boundary
            else None
        )
        if previous_snapshot is None:
            items.append(
                SnapshotChangeHistoryItem(
                    date=snapshot.snapshot_at,
                    ruleset_version=snapshot.ruleset_version,
                    version_boundary=False,
                    confidence=confidence,
                    delta=None,
                    primary_driver=(
                        "Baseline snapshot"
                        if confidence is not None
                        else "Not available"
                    ),
                    comparison_unavailable_reason=(
                        LEGACY_RELEASE_CONFIDENCE_REASON
                        if snapshot.ruleset_version == 0
                        else None
                    ),
                )
            )
        elif version_boundary:
            items.append(
                SnapshotChangeHistoryItem(
                    date=snapshot.snapshot_at,
                    ruleset_version=snapshot.ruleset_version,
                    version_boundary=True,
                    confidence=confidence,
                    delta=None,
                    primary_driver="Ruleset boundary",
                    comparison_unavailable_reason=RULESET_MISMATCH_REASON,
                )
            )
        elif classification_reason is not None:
            items.append(
                SnapshotChangeHistoryItem(
                    date=snapshot.snapshot_at,
                    ruleset_version=snapshot.ruleset_version,
                    version_boundary=False,
                    confidence=confidence,
                    delta=None,
                    primary_driver="Classification boundary",
                    comparison_unavailable_reason=classification_reason,
                )
            )
        elif confidence is None or previous_snapshot.confidence_score is None:
            unavailable_reason = (
                INCONCLUSIVE_RELEASE_CONFIDENCE_REASON
                if snapshot.confidence_status == "PARTIAL"
                or previous_snapshot.confidence_status == "PARTIAL"
                else UNAVAILABLE_RELEASE_CONFIDENCE_REASON
            )
            items.append(
                SnapshotChangeHistoryItem(
                    date=snapshot.snapshot_at,
                    ruleset_version=snapshot.ruleset_version,
                    version_boundary=False,
                    confidence=confidence,
                    delta=None,
                    primary_driver="Not available",
                    comparison_unavailable_reason=unavailable_reason,
                )
            )
        else:
            comparison = SnapshotComparisonService.compare_release_snapshots(
                current_snapshot=snapshot,
                previous_snapshot=previous_snapshot,
            )
            items.append(
                SnapshotChangeHistoryItem(
                    date=snapshot.snapshot_at,
                    ruleset_version=snapshot.ruleset_version,
                    version_boundary=False,
                    confidence=confidence,
                    delta=comparison.confidence_delta,
                    primary_driver=SnapshotComparisonService.primary_driver(comparison),
                    comparison_unavailable_reason=None,
                )
            )
        previous_snapshot = snapshot
    return items


class ReleaseMetricsResponseService:
    """Load stored release metrics and assemble their public response."""

    def get_metrics(
        self,
        *,
        session: Session,
        release_id: str,
        current_time: datetime,
    ) -> ReleaseMetricsResponse:
        release = ReleaseRepository.get_release_by_id(
            session=session, release_id=release_id
        )
        if release is None:
            raise ApplicationNotFoundError(f"Release '{release_id}' not found")

        field_mapper = JiraFieldMapper(get_settings())
        metric_availability = MetricAvailabilityService.build_release_availability(
            session=session,
            release_id=release_id,
            field_mapper=field_mapper,
        )
        snapshot = MetricRepository.get_latest_snapshot(
            session=session, release_id=release_id
        )
        if snapshot is None:
            computation_status, unavailable_reason = (
                MetricAvailabilityService.computation_state(
                    metric_availability,
                    is_computed=False,
                    empty_scope_reason=UNAVAILABLE_REASON_RELEASE_EMPTY,
                )
            )
            return ReleaseMetricsResponse(
                release_id=release_id,
                ruleset_version=None,
                ruleset_label=None,
                calculation_provenance=None,
                snapshot_at=None,
                computation_status=computation_status,
                unavailable_reason=unavailable_reason,
                metrics=MetricValues(
                    open_blockers=None,
                    open_high_severity_bugs=None,
                    scope_completed_pct=None,
                    completed_tickets=None,
                    scope_churn_7d_pct=None,
                    scope_added_7d_count=None,
                    scope_removed_7d_count=None,
                    median_cycle_time_days=None,
                    reopen_rate_pct=None,
                ),
                metric_issue_keys=MetricIssueKeys(
                    open_blockers=[],
                    open_high_severity_bugs=[],
                    completed_tickets=[],
                ),
                metric_names=RELEASE_METRIC_NAMES,
                metric_availability=metric_availability,
                metric_thresholds=None,
                confidence_score=None,
                confidence_breakdown=None,
                biggest_driver=None,
                recommendations=[],
                is_computed=False,
                snapshot_age_hours=None,
            )

        snapshot_at = snapshot.snapshot_at
        if snapshot_at.tzinfo is None:
            snapshot_at = snapshot_at.replace(tzinfo=UTC)
        else:
            snapshot_at = snapshot_at.astimezone(UTC)
        normalized_current_time = current_time
        if normalized_current_time.tzinfo is None:
            normalized_current_time = normalized_current_time.replace(tzinfo=UTC)
        else:
            normalized_current_time = normalized_current_time.astimezone(UTC)
        snapshot_age_hours = round(
            (normalized_current_time - snapshot_at).total_seconds() / 3600.0,
            3,
        )

        has_release_tickets = metric_availability.context.has_tickets
        computation_status, unavailable_reason = (
            MetricAvailabilityService.computation_state(
                metric_availability,
                is_computed=True,
                empty_scope_reason=UNAVAILABLE_REASON_RELEASE_EMPTY,
            )
        )
        provenance = snapshot.calculation_provenance or {}
        stored_availability = provenance.get("availability")
        if snapshot.ruleset_version > 0 and isinstance(stored_availability, dict):
            metric_availability = type(metric_availability).model_validate(
                stored_availability
            )
            stored_computation_status = provenance.get("computation_status")
            if stored_computation_status in {
                "COMPUTED",
                "PARTIAL",
                "NOT_COMPUTED",
            }:
                computation_status = cast(
                    ComputationStatus,
                    stored_computation_status,
                )
            if "unavailable_reason" in provenance:
                stored_unavailable_reason = provenance["unavailable_reason"]
                if stored_unavailable_reason is None or isinstance(
                    stored_unavailable_reason,
                    str,
                ):
                    unavailable_reason = stored_unavailable_reason
        confidence_score = (
            snapshot.confidence_score
            if has_release_tickets and snapshot.ruleset_version > 0
            else None
        )
        component_outputs = provenance.get("component_outputs", {})
        return ReleaseMetricsResponse(
            release_id=release_id,
            ruleset_version=snapshot.ruleset_version,
            ruleset_label=(
                "Unversioned legacy result"
                if snapshot.ruleset_version == 0
                else f"Ruleset v{snapshot.ruleset_version}"
            ),
            calculation_provenance=provenance,
            snapshot_at=snapshot.snapshot_at,
            computation_status=computation_status,
            unavailable_reason=unavailable_reason,
            metrics=MetricValues(
                open_blockers=_stored_metric_value(
                    snapshot,
                    "open_blockers",
                    snapshot.open_blockers,
                ),
                open_high_severity_bugs=_stored_metric_value(
                    snapshot,
                    "open_high_severity_bugs",
                    snapshot.open_high_severity_bugs,
                ),
                scope_completed_pct=_stored_metric_value(
                    snapshot,
                    "scope_completed_pct",
                    snapshot.scope_completed_pct,
                ),
                completed_tickets=_stored_metric_value(
                    snapshot,
                    "completed_tickets",
                    snapshot.completed_tickets,
                ),
                scope_churn_7d_pct=_stored_metric_value(
                    snapshot,
                    "scope_churn_7d_pct",
                    snapshot.scope_churn_7d_pct,
                ),
                scope_added_7d_count=_stored_metric_value(
                    snapshot,
                    "scope_added_7d_count",
                    snapshot.scope_added_7d_count,
                ),
                scope_removed_7d_count=_stored_metric_value(
                    snapshot,
                    "scope_removed_7d_count",
                    snapshot.scope_removed_7d_count,
                ),
                median_cycle_time_days=snapshot.median_cycle_time_days,
                reopen_rate_pct=snapshot.reopen_rate_pct,
            ),
            metric_issue_keys=MetricIssueKeys(
                open_blockers=snapshot.open_blocker_issue_keys,
                open_high_severity_bugs=snapshot.open_high_severity_bug_issue_keys,
                completed_tickets=cast(
                    list[str],
                    (
                        issue_key_evidence.get("completed_tickets", [])
                        if snapshot.ruleset_version > 0
                        and isinstance(
                            issue_key_evidence := provenance.get(
                                "issue_key_evidence"
                            ),
                            dict,
                        )
                        else []
                    ),
                ),
            ),
            metric_names=RELEASE_METRIC_NAMES,
            metric_availability=metric_availability,
            metric_thresholds=(
                MetricThresholds.model_validate(provenance.get("thresholds", {}))
                if snapshot.ruleset_version > 0 and provenance.get("thresholds")
                else None
            ),
            confidence_score=confidence_score,
            confidence_breakdown=(
                component_outputs.get("confidence_breakdown")
                if isinstance(component_outputs, dict)
                else None
            ),
            biggest_driver=(
                component_outputs.get("biggest_driver")
                if isinstance(component_outputs, dict)
                else None
            ),
            recommendations=(
                RecommendationEngine.build_release_recommendations(
                    snapshot,
                    metric_availability=metric_availability,
                )
                if has_release_tickets
                else []
            ),
            is_computed=True,
            snapshot_age_hours=snapshot_age_hours,
        )

    def get_charts(
        self,
        *,
        session: Session,
        release_id: str,
        limit: int,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> ReleaseChartsResponse:
        release = ReleaseRepository.get_release_by_id(
            session=session, release_id=release_id
        )
        if release is None:
            raise ApplicationNotFoundError(f"Release '{release_id}' not found")
        if from_at is not None and to_at is not None and from_at > to_at:
            raise ApplicationValidationError(
                "'from' must be less than or equal to 'to'"
            )

        snapshots = MetricRepository.list_snapshots_for_release(
            session=session,
            release_id=release_id,
            limit=limit,
            from_at=from_at,
            to_at=to_at,
        )
        has_release_tickets = (
            ReleaseRepository.count_release_issues(
                session=session, release_id=release_id
            )
            > 0
        )
        release_gate_values = (
            {
                snapshot.id: _build_release_gate_values(snapshot)
                for snapshot in snapshots
            }
            if has_release_tickets
            else {}
        )
        version_boundaries = {
            snapshot.id: (
                index > 0
                and snapshots[index - 1].ruleset_version != snapshot.ruleset_version
            )
            for index, snapshot in enumerate(snapshots)
        }

        def chart_point(snapshot, value) -> ChartPoint:
            return ChartPoint(
                snapshot_at=snapshot.snapshot_at,
                value=value,
                ruleset_version=snapshot.ruleset_version,
                version_boundary=version_boundaries[snapshot.id],
            )

        return ReleaseChartsResponse(
            release_id=release_id,
            series=MetricSeries(
                open_blockers=[
                    chart_point(
                        snapshot,
                        _stored_metric_value(
                            snapshot, "open_blockers", snapshot.open_blockers
                        ),
                    )
                    for snapshot in snapshots
                ],
                open_high_severity_bugs=[
                    chart_point(
                        snapshot,
                        _stored_metric_value(
                            snapshot,
                            "open_high_severity_bugs",
                            snapshot.open_high_severity_bugs,
                        ),
                    )
                    for snapshot in snapshots
                ],
                scope_completed_pct=[
                    chart_point(
                        snapshot,
                        _stored_metric_value(
                            snapshot,
                            "scope_completed_pct",
                            snapshot.scope_completed_pct,
                        ),
                    )
                    for snapshot in snapshots
                ],
                completed_tickets=[
                    chart_point(
                        snapshot,
                        _stored_metric_value(
                            snapshot,
                            "completed_tickets",
                            snapshot.completed_tickets,
                        ),
                    )
                    for snapshot in snapshots
                ],
                scope_churn_7d_pct=[
                    chart_point(
                        snapshot,
                        _stored_metric_value(
                            snapshot,
                            "scope_churn_7d_pct",
                            snapshot.scope_churn_7d_pct,
                        ),
                    )
                    for snapshot in snapshots
                ],
                scope_added_7d_count=[
                    chart_point(
                        snapshot,
                        _stored_metric_value(
                            snapshot,
                            "scope_added_7d_count",
                            snapshot.scope_added_7d_count,
                        ),
                    )
                    for snapshot in snapshots
                ],
                scope_removed_7d_count=[
                    chart_point(
                        snapshot,
                        _stored_metric_value(
                            snapshot,
                            "scope_removed_7d_count",
                            snapshot.scope_removed_7d_count,
                        ),
                    )
                    for snapshot in snapshots
                ],
                median_cycle_time_days=[
                    chart_point(snapshot, snapshot.median_cycle_time_days)
                    for snapshot in snapshots
                ],
                reopen_rate_pct=[
                    chart_point(snapshot, snapshot.reopen_rate_pct)
                    for snapshot in snapshots
                ],
                confidence_score=[
                    chart_point(
                        snapshot,
                        (
                            snapshot.confidence_score
                            if has_release_tickets and snapshot.ruleset_version > 0
                            else None
                        ),
                    )
                    for snapshot in snapshots
                ],
                gates_passed_count=[
                    chart_point(
                        snapshot,
                        (
                            release_gate_values[snapshot.id][0]
                            if has_release_tickets
                            else None
                        ),
                    )
                    for snapshot in snapshots
                ],
                readiness_pct=[
                    chart_point(
                        snapshot,
                        (
                            release_gate_values[snapshot.id][2]
                            if has_release_tickets
                            else None
                        ),
                    )
                    for snapshot in snapshots
                ],
            ),
            metric_names=RELEASE_CHART_METRIC_NAMES,
            point_count=len(snapshots),
            release_gates_total=(
                max((values[1] for values in release_gate_values.values()), default=0)
                if has_release_tickets
                else 0
            ),
        )

    def get_snapshot_comparison(
        self,
        *,
        session: Session,
        release_id: str,
        baseline: SnapshotBaseline,
    ) -> SnapshotComparisonResponse:
        release = ReleaseRepository.get_release_by_id(
            session=session, release_id=release_id
        )
        if release is None:
            raise ApplicationNotFoundError(f"Release '{release_id}' not found")

        current_snapshot = MetricRepository.get_latest_snapshot(
            session=session,
            release_id=release_id,
        )
        if current_snapshot is None:
            return _empty_snapshot_comparison(release_id, baseline, None)

        baseline_snapshot = _select_release_baseline_snapshot(
            session=session,
            release_id=release_id,
            current_snapshot=current_snapshot,
            baseline=baseline,
        )
        if baseline_snapshot is None:
            response = _empty_snapshot_comparison(
                release_id,
                baseline,
                current_snapshot.snapshot_at,
            )
            response.current_ruleset_version = current_snapshot.ruleset_version
            return response

        unavailable_reason = None
        if current_snapshot.ruleset_version != baseline_snapshot.ruleset_version:
            unavailable_reason = RULESET_MISMATCH_REASON
        elif current_snapshot.ruleset_version == 0:
            unavailable_reason = LEGACY_RELEASE_CONFIDENCE_REASON
        else:
            unavailable_reason = (
                SnapshotComparisonService.classification_unavailable_reason(
                    current_snapshot,
                    baseline_snapshot,
                )
            )
            if unavailable_reason is None and (
                current_snapshot.confidence_score is None
                or baseline_snapshot.confidence_score is None
            ):
                unavailable_reason = (
                    INCONCLUSIVE_RELEASE_CONFIDENCE_REASON
                    if current_snapshot.confidence_status == "PARTIAL"
                    or baseline_snapshot.confidence_status == "PARTIAL"
                    else UNAVAILABLE_RELEASE_CONFIDENCE_REASON
                )

        comparison = (
            SnapshotDeltaComparison(confidence_delta=None, contributors=[])
            if unavailable_reason is not None
            else SnapshotComparisonService.compare_release_snapshots(
                current_snapshot=current_snapshot,
                previous_snapshot=baseline_snapshot,
            )
        )
        return SnapshotComparisonResponse(
            entity_id=release_id,
            baseline=baseline,
            current_snapshot_at=current_snapshot.snapshot_at,
            baseline_snapshot_at=baseline_snapshot.snapshot_at,
            has_baseline=True,
            current_ruleset_version=current_snapshot.ruleset_version,
            baseline_ruleset_version=baseline_snapshot.ruleset_version,
            unavailable_reason=unavailable_reason,
            comparison=comparison,
        )

    def get_snapshot_change_history(
        self,
        *,
        session: Session,
        release_id: str,
        limit: int,
    ) -> SnapshotChangeHistoryResponse:
        release = ReleaseRepository.get_release_by_id(
            session=session, release_id=release_id
        )
        if release is None:
            raise ApplicationNotFoundError(f"Release '{release_id}' not found")
        snapshots = MetricRepository.list_snapshots_for_release(
            session=session,
            release_id=release_id,
            limit=limit,
        )
        return SnapshotChangeHistoryResponse(
            entity_id=release_id,
            items=_build_release_history_items(snapshots),
        )
