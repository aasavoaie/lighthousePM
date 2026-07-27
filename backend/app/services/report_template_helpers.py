from datetime import UTC, datetime
from collections.abc import Mapping

from app.metric_catalog import (
    METRIC_CATALOG_BY_KEY,
    RELEASE_THRESHOLD_METADATA,
    MetricDefinition,
    metrics_for_scope,
)
from app.models import MetricSnapshot, Sprint, SprintMetricSnapshot
from app.schemas.availability import MetricAvailability
from app.schemas.confidence import ConfidenceBreakdown
from app.schemas.drivers import DriverAnalysis
from app.services.report_data_preparation import stored_metric_availability
from app.services.report_document_models import ReportSection
from app.services.report_formatting import format_datetime
from app.services.report_theme import pdf_color


SPRINT_STORY_POINT_UNAVAILABLE_MESSAGE = "Delivery confidence requires at least 50% of sprint tickets to have valid story points."
RELEASE_NO_TICKETS_MESSAGE = "No tickets are available for this scope."
RELEASE_NO_STORY_POINTS_MESSAGE = "No tickets in this scope have story points."


def _documentation_sections_from_markdown(
    markdown: str,
) -> tuple[str, list[ReportSection]]:
    document_title = "Lighthouse PM Documentation"
    sections: list[ReportSection] = []
    current_title: str | None = None
    current_lines: list[str] = []
    current_bullets: list[str] = []
    current_heading_color: tuple[float, float, float] | None = None
    current_include_empty = False
    current_page = ""

    def flush_section() -> None:
        nonlocal \
            current_title, \
            current_lines, \
            current_bullets, \
            current_heading_color, \
            current_include_empty
        if current_title and (
            current_lines or current_bullets or current_include_empty
        ):
            sections.append(
                ReportSection(
                    title=current_title,
                    lines=current_lines,
                    bullets=current_bullets,
                    heading_color=current_heading_color,
                )
            )
        current_title = None
        current_lines = []
        current_bullets = []
        current_heading_color = None
        current_include_empty = False

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# "):
            document_title = line[2:].strip()
            continue
        if line.startswith("## "):
            flush_section()
            current_page = line[3:].strip()
            current_title = current_page
            current_heading_color = _documentation_heading_color(current_page)
            current_include_empty = True
            continue
        if line.startswith("### "):
            flush_section()
            heading = line[4:].strip()
            current_title = heading
            current_heading_color = _documentation_heading_color(current_page)
            continue
        if line.startswith("#### "):
            flush_section()
            heading = line[5:].strip()
            current_title = heading
            current_heading_color = _documentation_heading_color(current_page)
            continue
        if line.startswith("- "):
            current_bullets.append(line[2:].strip())
            continue
        if "." in line:
            number, text = line.split(".", 1)
            if number.isdigit() and text.startswith(" "):
                current_bullets.append(text.strip())
                continue
        current_lines.append(line)

    flush_section()
    return document_title, sections


def _documentation_heading_color(page: str) -> tuple[float, float, float] | None:
    colors = {
        "Overview": "#4b22d4",
        "Releases": "#0b6bcb",
        "Sprints": "#237445",
    }
    color = colors.get(page)
    return pdf_color(color).rgb if color else None


def format_short_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%m-%d %H:%M")


def format_percent(value: object) -> str:
    if not isinstance(value, int | float):
        return "N/A"
    return f"{round(float(value), 2)}%"


def format_number(value: object) -> str:
    if not isinstance(value, int | float):
        return "N/A"
    if float(value).is_integer():
        return str(int(value))
    return str(round(float(value), 2))


def report_metric_definition(metric_key: str) -> MetricDefinition:
    """Return report metadata for one cataloged metric."""

    definition = METRIC_CATALOG_BY_KEY[metric_key]
    if not definition.report_participation:
        raise ValueError(f"Metric '{metric_key}' does not participate in reports.")
    return definition


def report_metric_label(metric_key: str) -> str:
    return report_metric_definition(metric_key).label


def format_report_metric_value(
    metric_key: str, value: object, *, include_unit: bool = True
) -> str:
    """Format a report value from its catalog unit and formatting rule."""

    definition = report_metric_definition(metric_key)
    if not isinstance(value, int | float):
        return "N/A"

    numeric_value = float(value)
    if definition.formatting == "integer":
        formatted_value = str(round(numeric_value))
    elif definition.formatting == "decimal_1":
        formatted_value = f"{numeric_value:.1f}"
    elif definition.formatting == "decimal_2":
        formatted_value = f"{numeric_value:.2f}"
    elif definition.formatting == "decimal_4":
        formatted_value = f"{numeric_value:.4f}"
    elif definition.formatting == "percent_2":
        formatted_value = f"{numeric_value:.2f}%"
    else:
        raise ValueError(
            f"Unsupported catalog formatting rule: {definition.formatting}"
        )

    if definition.unit == "days" and include_unit:
        return f"{formatted_value} days"
    if definition.unit in {"percent", "score"} and not formatted_value.endswith("%"):
        return f"{formatted_value}%"
    return formatted_value


def format_delta(value: float) -> str:
    if value == 0:
        return "0%"
    return f"{'+' if value > 0 else ''}{round(value, 2)}%"


def confidence_band(value: object) -> str:
    if not isinstance(value, int | float):
        return "Not computed"
    if value >= RELEASE_THRESHOLD_METADATA["confidence_score_green_min"]:
        return "High Confidence"
    if value >= RELEASE_THRESHOLD_METADATA["confidence_score_yellow_min"]:
        return "Medium Confidence"
    return "Low Confidence"


def breakdown_rows(breakdown) -> list[tuple[str, str]]:
    if breakdown is None:
        return [("Status", "No confidence breakdown available.")]
    rows = [("Total score", format_percent(breakdown.totalScore))]
    rows.extend(
        (
            component.name,
            f"{format_percent(component.score)} of {format_percent(component.maxScore)} | {component.status} | {component.explanation}",
        )
        for component in breakdown.components
    )
    return rows


def driver_rows(driver) -> list[tuple[str, str]]:
    if driver is None:
        return [("Status", "No biggest driver is available.")]
    return [
        ("Title", driver.title),
        ("Category", driver.category),
        ("Impact", format_percent(driver.impact)),
        ("Contribution", format_percent(driver.contributionPercent)),
        ("Explanation", driver.explanation),
        ("Recommendation", driver.recommendation),
    ]


def recommendation_bullets(recommendations, limit: int | None = None) -> list[str]:
    if not recommendations:
        return ["No deterministic recommended actions are active for this snapshot."]
    selected_recommendations = (
        recommendations if limit is None else recommendations[:limit]
    )
    return [
        f"P{item.priority} {item.title}: {item.description} Confidence impact {item.confidenceImpact}%, effort {item.effort}, category {item.category}."
        for item in selected_recommendations
    ]


def release_top_risk_bullets(readiness: Mapping[str, object], limit: int) -> list[str]:
    risks: list[str] = []
    for key in ("critical_risks", "warnings"):
        items = readiness.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("message"):
                risks.append(str(item["message"]))
    reasons = readiness.get("reasons", [])
    if isinstance(reasons, list):
        risks.extend(str(reason) for reason in reasons)
    deduped = list(dict.fromkeys(risks))
    return deduped[:limit] or [
        "No active top release risks found in the latest computed signal."
    ]


def decision_recommendation_lines(readiness: Mapping[str, object]) -> list[str]:
    signal = str(readiness.get("signal") or "").upper()
    if signal == "GREEN":
        return [
            "Release can proceed from the current deterministic risk posture. Continue monitoring gates and confidence before final approval."
        ]
    if signal == "YELLOW":
        return [
            "Proceed only with named mitigation owners for the top risks. Recheck confidence after recommended actions are completed."
        ]
    if signal == "RED":
        return [
            "Do not release until red-level risks are resolved and a fresh LighthousePM snapshot confirms improved confidence."
        ]
    if signal == "INCONCLUSIVE":
        return [
            "Do not make a release decision until the missing required Jira metric inputs are completed and a fresh snapshot is computed."
        ]
    return [
        "Do not make a release decision until release metrics and signal have been computed."
    ]


def _overview_release_snapshot_label(snapshot: MetricSnapshot | None) -> str:
    return (
        format_datetime(snapshot.snapshot_at)
        if snapshot
        else "No snapshot available yet."
    )


def _overview_sprint_snapshot_label(
    sprint: Sprint | None, snapshot: SprintMetricSnapshot | None
) -> str:
    if sprint is None:
        return "No sprint snapshot available yet."
    return (
        format_datetime(snapshot.snapshot_at)
        if snapshot
        else "No sprint snapshot available yet."
    )


def overview_sprint_metric_rows(
    sprint: Sprint | None,
    snapshot: SprintMetricSnapshot | None,
    has_story_points: bool = True,
    availability: MetricAvailability | None = None,
) -> list[tuple[str, str]]:
    if sprint is None:
        return [("Status", "No active sprint is available for the overview dashboard.")]
    if snapshot is None:
        return [
            ("Sprint", sprint.name),
            ("State", sprint.state),
            ("Status", "No sprint snapshot available yet."),
        ]
    rows = [
        ("Sprint", sprint.name),
        ("State", sprint.state),
        ("Goal", sprint.goal or "N/A"),
        ("Start", format_datetime(sprint.start_date)),
        ("End", format_datetime(sprint.end_date)),
        *sprint_ticket_scope_rows(snapshot, availability),
        *sprint_work_state_rows(snapshot, availability),
        _catalog_snapshot_metric_row(snapshot, availability, "sprint.open_blockers"),
        _catalog_snapshot_metric_row(
            snapshot,
            availability,
            "sprint.open_high_severity_bugs",
            label=report_metric_label("sprint.open_high_severity_bugs")
            .removeprefix("Open ")
            .capitalize(),
        ),
        _catalog_snapshot_metric_row(snapshot, availability, "sprint.reopen_rate_pct"),
    ]
    rows.extend(_metric_explanation_rows(availability, "sprint.reopen_rate_pct"))
    if has_story_points:
        metric_key = "sprint.delivery_confidence_score"
        rows.append(
            (
                report_metric_label(metric_key),
                format_report_metric_value(
                    metric_key, snapshot.delivery_confidence_score
                ),
            )
        )
    else:
        rows.append(("Story-point metrics", SPRINT_STORY_POINT_UNAVAILABLE_MESSAGE))
    return rows


def overview_risk_bullets(
    readiness: Mapping[str, object],
    snapshot: MetricSnapshot | None,
    sprint_snapshot: SprintMetricSnapshot | None,
) -> list[str]:
    bullets = release_top_risk_bullets(readiness, limit=5)
    if snapshot is not None:
        bullets.extend(
            [
                f"Release blockers: {snapshot.open_blockers}.",
                f"Release high-severity bugs: {snapshot.open_high_severity_bugs}.",
                "Release scope churn: "
                f"{format_report_metric_value('release.scope_churn_7d_pct', snapshot.scope_churn_7d_pct)}.",
            ]
        )
    if sprint_snapshot is not None:
        bullets.extend(
            [
                f"Sprint blockers: {sprint_snapshot.open_blockers}.",
                f"Sprint high-severity bugs: {sprint_snapshot.open_high_severity_bugs}.",
                f"Sprint bugs created during sprint: {sprint_snapshot.bugs_created_during_sprint}.",
            ]
        )
    return list(dict.fromkeys(bullets)) or ["No active overview risk indicators found."]


def overview_signal_rows(readiness: Mapping[str, object]) -> list[tuple[str, str]]:
    reasons = readiness.get("reasons", [])
    reason_text = (
        ", ".join(str(reason) for reason in reasons)
        if isinstance(reasons, list)
        else "N/A"
    )
    return [
        ("Signal", str(readiness.get("signal") or "Not computed")),
        ("Status", str(readiness.get("status_label") or "Not computed")),
        (
            report_metric_label("release.confidence_score").removeprefix("Release "),
            format_report_metric_value(
                "release.confidence_score", readiness.get("confidence_score")
            ),
        ),
        (
            report_metric_label("release.readiness_pct"),
            format_report_metric_value(
                "release.readiness_pct", readiness.get("readiness_pct")
            ),
        ),
        ("Reasons", reason_text or "No signal reasons recorded."),
    ]


def overview_health_rows(
    readiness: Mapping[str, object],
    snapshot: MetricSnapshot | None,
    sprint_snapshot: SprintMetricSnapshot | None,
    sprint_has_story_points: bool = True,
) -> list[tuple[str, str]]:
    gates_value = readiness.get("release_gates", [])
    gates = gates_value if isinstance(gates_value, list) else []
    gate_count = len(gates)
    gates_passed = sum(
        1 for gate in gates if isinstance(gate, dict) and gate.get("passed") is True
    )
    return [
        (
            "Release gates passed",
            f"{gates_passed} of {gate_count}" if gate_count else "N/A",
        ),
        ("Release confidence band", confidence_band(readiness.get("confidence_score"))),
        (
            f"Release {report_metric_label('release.scope_completed_pct').lower()}",
            format_report_metric_value(
                "release.scope_completed_pct",
                snapshot.scope_completed_pct if snapshot else None,
            ),
        ),
        (
            f"Release {report_metric_label('release.median_cycle_time_days').removeprefix('Median ').lower()}",
            format_report_metric_value(
                "release.median_cycle_time_days",
                snapshot.median_cycle_time_days if snapshot else None,
                include_unit=False,
            ),
        ),
        (
            "Sprint delivery band",
            confidence_band(
                sprint_snapshot.delivery_confidence_score
                if sprint_snapshot and sprint_has_story_points
                else None
            ),
        ),
        (
            f"Sprint {report_metric_label('sprint.completed_scope_pct').lower()}",
            format_report_metric_value(
                "sprint.completed_scope_pct",
                sprint_snapshot.completed_scope_pct if sprint_snapshot else None,
            ),
        ),
        (
            f"Sprint {report_metric_label('sprint.reopen_rate_pct').lower()}",
            format_report_metric_value(
                "sprint.reopen_rate_pct",
                sprint_snapshot.reopen_rate_pct if sprint_snapshot else None,
            ),
        ),
    ]


def overview_recommendation_bullets(
    release_recommendations, sprint_recommendations
) -> list[str]:
    bullets = [
        f"Release: {item}"
        for item in recommendation_bullets(release_recommendations, limit=3)
    ]
    if sprint_recommendations:
        bullets.extend(
            f"Sprint: {item}"
            for item in recommendation_bullets(sprint_recommendations, limit=3)
        )
    return bullets or [
        "No deterministic recommendations are active for the overview dashboard."
    ]


def _sprint_confidence_available(snapshot: SprintMetricSnapshot | None) -> bool:
    return bool(
        snapshot
        and snapshot.delivery_confidence_status in {"PARTIAL", "COMPUTED"}
        and snapshot.delivery_confidence_score is not None
    )


def _sprint_confidence_status_rows(
    snapshot: SprintMetricSnapshot | None,
) -> list[tuple[str, str]]:
    if snapshot is None:
        return [("Status", "Delivery confidence has not been computed yet.")]
    rows = [
        ("Status", snapshot.delivery_confidence_status.replace("_", " ").title()),
        ("Story-point coverage", format_percent(snapshot.story_point_coverage_pct)),
    ]
    rows.extend(
        ("Explanation" if index == 0 else "Coverage guidance", explanation)
        for index, explanation in enumerate(snapshot.delivery_confidence_explanations)
    )
    return rows


def _first_last_delta(values: list[float | None]) -> float | None:
    numeric_values = [
        float(value) for value in values if isinstance(value, int | float)
    ]
    if len(numeric_values) < 2:
        return None
    return numeric_values[-1] - numeric_values[0]


def _release_confidence_for_report(
    snapshot: MetricSnapshot,
    release_availability: MetricAvailability | None = None,
) -> float | None:
    if (
        release_availability is not None
        and not release_availability.context.has_tickets
    ):
        return None
    return snapshot.confidence_score if snapshot.ruleset_version > 0 else None


def _stored_release_confidence_artifacts(
    snapshot: MetricSnapshot | None,
) -> tuple[ConfidenceBreakdown | None, DriverAnalysis | None]:
    if snapshot is None or snapshot.ruleset_version == 0:
        return None, None
    outputs = (snapshot.calculation_provenance or {}).get("component_outputs", {})
    if not isinstance(outputs, dict):
        return None, None
    breakdown = outputs.get("confidence_breakdown")
    driver = outputs.get("biggest_driver")
    return (
        ConfidenceBreakdown.model_validate(breakdown)
        if isinstance(breakdown, dict)
        else None,
        DriverAnalysis.model_validate(driver) if isinstance(driver, dict) else None,
    )


def _stored_sprint_confidence_artifacts(
    snapshot: SprintMetricSnapshot | None,
) -> tuple[ConfidenceBreakdown | None, DriverAnalysis | None]:
    if snapshot is None or snapshot.ruleset_version == 0:
        return None, None
    outputs = (snapshot.calculation_provenance or {}).get("component_outputs", {})
    if not isinstance(outputs, dict):
        return None, None
    breakdown = outputs.get("confidence_breakdown")
    driver = outputs.get("biggest_driver")
    return (
        ConfidenceBreakdown.model_validate(breakdown)
        if isinstance(breakdown, dict)
        else None,
        DriverAnalysis.model_validate(driver) if isinstance(driver, dict) else None,
    )


def _ruleset_label(snapshot: MetricSnapshot | SprintMetricSnapshot | None) -> str:
    if snapshot is None:
        return "N/A"
    if snapshot.ruleset_version == 0:
        return "Unversioned legacy result (v0)"
    return f"Ruleset v{snapshot.ruleset_version}"


def gate_rows(gates: object) -> list[tuple[str, str]]:
    if not isinstance(gates, list) or not gates:
        return [("Status", "No release gates available.")]
    rows: list[tuple[str, str]] = []
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        state = "Passed" if gate.get("passed") else "Not passed"
        rows.append(
            (
                str(gate.get("label") or gate.get("metric_name") or "Gate"),
                f"{state} | value {format_number(gate.get('value'))} {gate.get('comparison', '')} {format_number(gate.get('threshold'))}",
            )
        )
    return rows or [("Status", "No release gates available.")]


def release_metric_rows(
    snapshot: MetricSnapshot | None,
    availability: MetricAvailability | None = None,
) -> list[tuple[str, str]]:
    if snapshot is None:
        return [("Status", "No release metrics have been computed yet.")]
    rows = []
    if availability is not None and not availability.context.has_tickets:
        rows.append(("Status", RELEASE_NO_TICKETS_MESSAGE))
    report_metrics = (
        metric
        for metric in metrics_for_scope("release")
        if metric.api_location == "metric_values" and metric.report_participation
    )
    rows.extend(
        (
            metric.label,
            _release_metric_value(
                snapshot,
                availability,
                metric.api_field,
                lambda value, metric_key=metric.key: format_report_metric_value(
                    metric_key, value
                ),
            ),
        )
        for metric in report_metrics
    )
    rows.extend(_metric_explanation_rows(availability, "release.reopen_rate_pct"))
    if (
        availability is not None
        and availability.context.has_tickets
        and not availability.context.has_story_points
    ):
        rows.append(("Story-point metrics", f"N/A | {RELEASE_NO_STORY_POINTS_MESSAGE}"))
    return rows


def _release_metric_value(
    snapshot: MetricSnapshot,
    availability: MetricAvailability | None,
    metric_name: str,
    formatter,
) -> str:
    item = availability.metrics.get(metric_name) if availability is not None else None
    if item is not None and not item.available:
        return f"N/A | {item.reason or 'Metric is unavailable.'}"
    return formatter(getattr(snapshot, metric_name))


def _snapshot_metric_value(
    snapshot: MetricSnapshot | SprintMetricSnapshot,
    availability: MetricAvailability | None,
    metric_name: str,
    formatter,
) -> str:
    item = availability.metrics.get(metric_name) if availability is not None else None
    if item is not None and not item.available:
        explanation = item.explanations[0] if item.explanations else item.reason
        return f"N/A | {explanation or 'Metric is unavailable.'}"
    return formatter(getattr(snapshot, metric_name))


def _catalog_snapshot_metric_row(
    snapshot: MetricSnapshot | SprintMetricSnapshot,
    availability: MetricAvailability | None,
    metric_key: str,
    *,
    label: str | None = None,
) -> tuple[str, str]:
    definition = report_metric_definition(metric_key)
    return (
        label or definition.label,
        _snapshot_metric_value(
            snapshot,
            availability,
            definition.api_field,
            lambda value: format_report_metric_value(metric_key, value),
        ),
    )


def _metric_explanation_rows(
    availability: MetricAvailability | None,
    metric_key: str,
) -> list[tuple[str, str]]:
    definition = report_metric_definition(metric_key)
    item = (
        availability.metrics.get(definition.api_field)
        if availability is not None
        else None
    )
    if item is None:
        return []
    repeated_event_explanations = [
        explanation
        for explanation in item.explanations
        if explanation.startswith("Ticket ") and " was counted " in explanation
    ]
    return [
        (
            "Reopen event evidence"
            if index == 0
            else "Additional reopen event evidence",
            explanation,
        )
        for index, explanation in enumerate(repeated_event_explanations)
    ]


def sprint_velocity_rows(
    snapshot: SprintMetricSnapshot | None, has_story_points: bool = True
) -> list[tuple[str, str]]:
    if not has_story_points:
        return [("Status", SPRINT_STORY_POINT_UNAVAILABLE_MESSAGE)]
    if snapshot is None or not snapshot.delivery_confidence_inputs:
        return [("Status", "No velocity baseline is available.")]
    inputs = snapshot.delivery_confidence_inputs
    historical = inputs.get("historical_velocity")
    completed = inputs.get("completed_effective_points")
    velocity_health = None
    if (
        isinstance(historical, int | float)
        and historical > 0
        and isinstance(completed, int | float)
    ):
        velocity_health = round((completed / historical) * 100, 2)
    return [
        ("Historical velocity", format_number(historical)),
        ("Completed effective points", format_number(completed)),
        ("Velocity health", format_percent(velocity_health)),
        ("Baseline sprint count", format_number(inputs.get("baseline_sprint_count"))),
    ]


def sprint_scope_rows(
    snapshot: SprintMetricSnapshot | None, has_story_points: bool = True
) -> list[tuple[str, str]]:
    if snapshot is None or snapshot.scope_creep_evidence is None:
        return [("Status", "Scope movement has not been computed yet.")]
    evidence = snapshot.scope_creep_evidence
    rows = [
        ("Status", snapshot.scope_creep_status.replace("_", " ").title()),
        (
            report_metric_label("sprint.scope_creep_pct"),
            format_report_metric_value(
                "sprint.scope_creep_pct", snapshot.scope_creep_pct
            ),
        ),
        (
            "Initial commitment",
            format_number(evidence.get("initial_commitment_count")),
        ),
        ("Addition events", format_number(evidence.get("scope_added_count"))),
        ("Removal events", format_number(evidence.get("scope_removed_count"))),
        ("Net scope change", format_number(evidence.get("net_scope_change"))),
        ("Scope change count", format_number(evidence.get("scope_change_count"))),
    ]
    if has_story_points and snapshot.delivery_confidence_components:
        rows.append(
            (
                "Scope stability component",
                format_percent(
                    snapshot.delivery_confidence_components.get("scope_stability")
                ),
            )
        )
    rows.extend(
        ("Explanation", str(explanation))
        for explanation in (snapshot.scope_creep_explanations or [])
    )
    return rows


def sprint_workload_rows(
    snapshot: SprintMetricSnapshot | None,
) -> list[tuple[str, str]]:
    if snapshot is None or snapshot.workload_distribution_status is None:
        return [("Status", "Workload distribution has not been computed yet.")]
    evidence = snapshot.workload_distribution_evidence or {}
    top_assignee = evidence.get("top_assignee") or {}
    concentration_key = "sprint.workload_concentration_pct"
    concentration_label = (
        report_metric_label(concentration_key).removeprefix("Workload ").capitalize()
    )
    rows = [
        ("Status", snapshot.workload_distribution_status.replace("_", " ").title()),
        (
            concentration_label,
            format_report_metric_value(
                concentration_key, snapshot.workload_concentration_pct
            ),
        ),
        ("Risk band", str(evidence.get("risk_band") or "N/A").title()),
        ("Top assignee", str(top_assignee.get("assignee") or "N/A")),
        ("Top-assignee points", format_number(top_assignee.get("story_points"))),
        (
            "Total included active points",
            format_number(evidence.get("total_active_points")),
        ),
    ]
    rows.extend(
        ("Explanation" if index == 0 else "Additional explanation", explanation)
        for index, explanation in enumerate(
            snapshot.workload_distribution_explanations or []
        )
    )
    return rows


def sprint_quality_rows(
    snapshot: SprintMetricSnapshot | None,
    availability: MetricAvailability | None = None,
) -> list[tuple[str, str]]:
    if snapshot is None:
        return [("Status", "No sprint quality metrics have been computed yet.")]
    rows = [
        _catalog_snapshot_metric_row(
            snapshot, availability, "sprint.open_high_severity_bugs"
        ),
        _catalog_snapshot_metric_row(
            snapshot, availability, "sprint.bugs_created_during_sprint"
        ),
        _catalog_snapshot_metric_row(snapshot, availability, "sprint.reopen_rate_pct"),
        _catalog_snapshot_metric_row(
            snapshot, availability, "sprint.median_cycle_time_days"
        ),
    ]
    rows.extend(_metric_explanation_rows(availability, "sprint.reopen_rate_pct"))
    return rows


def sprint_ticket_scope_rows(
    snapshot: SprintMetricSnapshot | None,
    availability: MetricAvailability | None = None,
) -> list[tuple[str, str]]:
    if snapshot is None:
        return [
            (report_metric_label("sprint.committed_scope"), "N/A"),
            (report_metric_label("sprint.completed_scope_pct"), "N/A"),
        ]
    return [
        _catalog_snapshot_metric_row(snapshot, availability, "sprint.committed_scope"),
        _catalog_snapshot_metric_row(
            snapshot, availability, "sprint.completed_scope_pct"
        ),
    ]


def sprint_work_state_rows(
    snapshot: SprintMetricSnapshot | None,
    availability: MetricAvailability | None = None,
) -> list[tuple[str, str]]:
    if snapshot is None:
        return [
            (report_metric_label("sprint.in_progress_count"), "N/A"),
            (report_metric_label("sprint.not_started_count"), "N/A"),
            (report_metric_label("sprint.rollover_count"), "N/A"),
        ]
    rows = [
        _catalog_snapshot_metric_row(
            snapshot, availability, "sprint.in_progress_count"
        ),
        _catalog_snapshot_metric_row(
            snapshot, availability, "sprint.not_started_count"
        ),
        _catalog_snapshot_metric_row(snapshot, availability, "sprint.rollover_count"),
    ]
    for metric_key, label in (
        ("sprint.in_progress_count", "In-progress count evidence"),
        ("sprint.not_started_count", "Not-started count evidence"),
        ("sprint.rollover_count", "Unfinished closed-sprint scope evidence"),
    ):
        definition = report_metric_definition(metric_key)
        item = (
            availability.metrics.get(definition.api_field)
            if availability is not None
            else None
        )
        if item is not None and item.status == "PARTIAL":
            rows.extend((label, explanation) for explanation in item.explanations)
    return rows


def sprint_risk_bullets(
    snapshot: SprintMetricSnapshot | None,
    availability: MetricAvailability | None = None,
) -> list[str]:
    if snapshot is None:
        return ["No sprint risk metrics have been computed yet."]
    bullets: list[str] = []
    if snapshot.open_blockers > 0:
        bullets.append(f"{snapshot.open_blockers} open blockers require attention.")
    if snapshot.open_high_severity_bugs > 0:
        bullets.append(
            f"{snapshot.open_high_severity_bugs} open high-severity bugs add quality risk."
        )
    availability = availability or stored_metric_availability(snapshot)
    unfinished_item = (
        availability.metrics.get("rollover_count") if availability is not None else None
    )
    if snapshot.rollover_count is not None and snapshot.rollover_count > 0:
        bullets.append(
            f"{snapshot.rollover_count} current closed-sprint tickets are unfinished and require follow-up."
        )
    if unfinished_item is not None and unfinished_item.status == "PARTIAL":
        bullets.extend(unfinished_item.explanations)
    if unfinished_item is not None and unfinished_item.status == "NOT_APPLICABLE":
        bullets.append(
            "Unfinished closed-sprint scope is not applicable to this sprint state."
        )
    if bullets:
        return bullets
    if snapshot.rollover_count is None:
        explanation = (
            unfinished_item.explanations[0]
            if unfinished_item is not None and unfinished_item.explanations
            else "The metric is unavailable."
        )
        return [
            "No computed blocker or high-severity bug risk is active. "
            f"Unfinished closed-sprint scope is unavailable: {explanation}"
        ]
    return [
        "No blocker, high-severity bug, or unfinished closed-sprint risk is active in this snapshot."
    ]


def _sprint_component(snapshot: SprintMetricSnapshot, key: str) -> float | None:
    if snapshot.delivery_confidence_components is None:
        return None
    value = snapshot.delivery_confidence_components.get(key)
    return float(value) if isinstance(value, int | float) else None


def _sprint_input(snapshot: SprintMetricSnapshot, key: str) -> float | None:
    if snapshot.delivery_confidence_inputs is None:
        return None
    value = snapshot.delivery_confidence_inputs.get(key)
    return float(value) if isinstance(value, int | float) else None


# Imported after the pure helper functions so focused templates can reuse them
