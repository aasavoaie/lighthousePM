from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
import sys
import tomllib
from types import MappingProxyType
from typing import Mapping, cast

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import MetricSnapshot, Release, Sprint, SprintMetricSnapshot
from app.repositories.metric_repository import MetricRepository
from app.repositories.release_repository import ReleaseRepository
from app.repositories.signal_repository import SignalRepository
from app.repositories.sprint_repository import SprintRepository
from app.schemas.availability import MetricAvailability
from app.services.jira_field_mapper import JiraFieldMapper
from app.services.metric_availability_service import MetricAvailabilityService
from app.services.recommendation_engine import RecommendationEngine
from app.services.signal_service import SignalService
from app.services.snapshot_comparison_service import SnapshotComparisonService


RELEASE_NO_TICKETS_MESSAGE = "No tickets are available for this scope."


def _dict_items(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [
        cast(dict[str, object], item)
        for item in value
        if isinstance(item, dict)
    ]


@dataclass(frozen=True)
class PreparedSnapshotComparison:
    confidence_delta: float | None
    primary_driver: str


@dataclass(frozen=True)
class PreparedPortfolioData:
    project_key: str
    release_count: int
    active_release_count: int
    computed_release_count: int
    sprint_count: int
    active_sprint_count: int


@dataclass(frozen=True)
class PreparedReleaseReportData:
    release: Release
    snapshot: MetricSnapshot | None
    snapshots: tuple[MetricSnapshot, ...]
    availability: MetricAvailability
    readiness: Mapping[str, object]
    readiness_history: tuple[Mapping[str, object], ...]
    recommendations: tuple[object, ...]
    outlook: Mapping[str, object]
    risk_aging_evidence: Mapping[str, object]
    snapshot_comparison: PreparedSnapshotComparison | None
    version: str


@dataclass(frozen=True)
class PreparedSprintReportData:
    sprint: Sprint
    snapshot: SprintMetricSnapshot | None
    snapshots: tuple[SprintMetricSnapshot, ...]
    availability: MetricAvailability | None
    has_story_points: bool
    recommendations: tuple[object, ...]
    snapshot_comparison: PreparedSnapshotComparison | None
    version: str


@dataclass(frozen=True)
class PreparedOverviewReportData:
    release_data: PreparedReleaseReportData
    sprint: Sprint | None
    sprint_snapshot: SprintMetricSnapshot | None
    sprint_snapshots: tuple[SprintMetricSnapshot, ...]
    sprint_availability: MetricAvailability | None
    sprint_has_story_points: bool
    sprint_recommendations: tuple[object, ...]
    portfolio: PreparedPortfolioData
    version: str


@dataclass(frozen=True)
class PreparedDocumentationReportData:
    markdown: str
    version: str


class ReportDataPreparationService:
    """Load and derive deterministic report inputs without layout or PDF work."""

    def prepare_release(
        self,
        *,
        session: Session,
        release_id: str,
    ) -> PreparedReleaseReportData:
        release = ReleaseRepository.get_release_by_id(
            session=session,
            release_id=release_id,
        )
        if release is None:
            raise ValueError(f"Release '{release_id}' not found")
        return self._prepare_release(session=session, release=release)

    def prepare_sprint(
        self,
        *,
        session: Session,
        sprint_id: str,
    ) -> PreparedSprintReportData:
        sprint = SprintRepository.get_sprint_by_id(session=session, sprint_id=sprint_id)
        if sprint is None:
            raise ValueError(f"Sprint '{sprint_id}' not found")
        snapshot = SprintRepository.get_latest_metric_snapshot(
            session=session,
            sprint_id=sprint.sprint_id,
        )
        snapshots = tuple(
            SprintRepository.list_metric_snapshots_for_sprint(
                session=session,
                sprint_id=sprint.sprint_id,
                limit=30,
            )
        )
        has_story_points = _sprint_confidence_available(snapshot)
        recommendations = tuple(
            RecommendationEngine.build_sprint_recommendations(
                snapshot,
                include_story_point_rules=has_story_points,
            )
            if snapshot
            else []
        )
        return PreparedSprintReportData(
            sprint=sprint,
            snapshot=snapshot,
            snapshots=snapshots,
            availability=stored_metric_availability(snapshot),
            has_story_points=has_story_points,
            recommendations=recommendations,
            snapshot_comparison=_prepare_sprint_comparison(snapshots),
            version=application_version(),
        )

    def prepare_overview(
        self,
        *,
        session: Session,
        release_id: str,
    ) -> PreparedOverviewReportData:
        release_data = self.prepare_release(session=session, release_id=release_id)
        release = release_data.release
        sprint = SprintRepository.get_current_sprint(
            session=session,
            project_key=release.project_key,
        )
        sprint_snapshot = (
            SprintRepository.get_latest_metric_snapshot(
                session=session,
                sprint_id=sprint.sprint_id,
            )
            if sprint
            else None
        )
        sprint_snapshots = tuple(
            SprintRepository.list_metric_snapshots_for_sprint(
                session=session,
                sprint_id=sprint.sprint_id,
                limit=30,
            )
            if sprint
            else []
        )
        sprint_has_story_points = _sprint_confidence_available(sprint_snapshot)
        sprint_recommendations = tuple(
            RecommendationEngine.build_sprint_recommendations(
                sprint_snapshot,
                include_story_point_rules=sprint_has_story_points,
            )
            if sprint_snapshot
            else []
        )
        return PreparedOverviewReportData(
            release_data=release_data,
            sprint=sprint,
            sprint_snapshot=sprint_snapshot,
            sprint_snapshots=sprint_snapshots,
            sprint_availability=stored_metric_availability(sprint_snapshot),
            sprint_has_story_points=sprint_has_story_points,
            sprint_recommendations=sprint_recommendations,
            portfolio=self._prepare_portfolio(
                session=session,
                project_key=release.project_key,
            ),
            version=release_data.version,
        )

    def prepare_documentation(self) -> PreparedDocumentationReportData:
        return PreparedDocumentationReportData(
            markdown=_read_about_documentation(),
            version=application_version(),
        )

    def _prepare_release(
        self,
        *,
        session: Session,
        release: Release,
    ) -> PreparedReleaseReportData:
        snapshot = MetricRepository.get_latest_snapshot(
            session=session,
            release_id=release.release_id,
        )
        snapshots = tuple(
            MetricRepository.list_snapshots_for_release(
                session=session,
                release_id=release.release_id,
                limit=30,
            )
        )
        availability = _release_metric_availability(
            session=session,
            release_id=release.release_id,
            snapshot=snapshot,
        )
        readiness = self._prepare_release_readiness(
            session=session,
            release_id=release.release_id,
            snapshot=snapshot,
            availability=availability,
        )
        readiness_history = tuple(
            self._prepare_release_readiness(
                session=session,
                release_id=release.release_id,
                snapshot=item,
                availability=_release_metric_availability(
                    session=session,
                    release_id=release.release_id,
                    snapshot=item,
                ),
            )
            for item in snapshots
        )
        recommendations = tuple(
            RecommendationEngine.build_release_recommendations(
                snapshot,
                metric_availability=availability,
            )
            if snapshot
            else []
        )
        outlook = self._prepare_release_outlook(
            session=session,
            release=release,
            snapshot=snapshot,
            readiness=readiness,
        )
        risk_aging_evidence = self._prepare_risk_aging_evidence(
            session=session,
            release=release,
            snapshot=snapshot,
        )
        return PreparedReleaseReportData(
            release=release,
            snapshot=snapshot,
            snapshots=snapshots,
            availability=availability,
            readiness=readiness,
            readiness_history=readiness_history,
            recommendations=recommendations,
            outlook=outlook,
            risk_aging_evidence=risk_aging_evidence,
            snapshot_comparison=_prepare_release_comparison(snapshots),
            version=application_version(),
        )

    def _prepare_release_readiness(
        self,
        *,
        session: Session,
        release_id: str,
        snapshot: MetricSnapshot | None,
        availability: MetricAvailability,
    ) -> Mapping[str, object]:
        if snapshot is None:
            signal = SignalRepository.get_latest_signal(
                session=session,
                release_id=release_id,
            )
            return _read_only_mapping(
                {
                    "signal": signal.signal if signal else None,
                    "status_label": "Not computed",
                    "summary": "Metrics have not been computed yet for this release.",
                    "confidence_score": None,
                    "reasons": signal.reasons if signal else [],
                    "release_gates": [],
                    "critical_risks": [],
                    "warnings": [],
                    "readiness_pct": None,
                }
            )
        if not availability.context.has_tickets:
            return _read_only_mapping(
                {
                    "signal": None,
                    "status_label": "NOT COMPUTED",
                    "summary": (
                        "Release signal is not computed because no tickets are "
                        "available for this scope."
                    ),
                    "confidence_score": None,
                    "reasons": [RELEASE_NO_TICKETS_MESSAGE],
                    "release_gates": [],
                    "critical_risks": [],
                    "warnings": [],
                    "readiness_pct": None,
                }
            )
        signal_row = SignalRepository.get_signal_for_snapshot(
            session=session,
            release_id=release_id,
            metric_snapshot_id=snapshot.id,
            ruleset_version=snapshot.ruleset_version,
        )
        if snapshot.ruleset_version == 0:
            return _read_only_mapping(
                {
                    "signal": signal_row.signal if signal_row else None,
                    "status_label": "Unversioned legacy result",
                    "summary": (
                        "Legacy raw metrics are shown; derived release confidence "
                        "is unavailable."
                    ),
                    "confidence_score": None,
                    "reasons": signal_row.reasons if signal_row else [],
                    "release_gates": [],
                    "critical_risks": [],
                    "warnings": [],
                    "readiness_pct": None,
                }
            )
        details = dict(signal_row.readiness_evidence) if signal_row else {}
        details["release_gates"] = signal_row.release_gates if signal_row else []
        details["confidence_score"] = (
            signal_row.confidence_score if signal_row else snapshot.confidence_score
        )
        gates = _dict_items(details.get("release_gates", []))
        gate_count = len(gates)
        passed = sum(
            1
            for gate in gates
            if isinstance(gate, dict) and gate.get("passed") is True
        )
        details["reasons"] = signal_row.reasons if signal_row else []
        details["readiness_pct"] = (
            None
            if gate_count == 0 or snapshot.confidence_status == "PARTIAL"
            else round((passed / gate_count) * 100, 2)
        )
        return _read_only_mapping(details)

    def _prepare_release_outlook(
        self,
        *,
        session: Session,
        release: Release,
        snapshot: MetricSnapshot | None,
        readiness: Mapping[str, object],
    ) -> Mapping[str, object]:
        release_gates = _dict_items(readiness.get("release_gates", []))
        critical_risks = _dict_items(readiness.get("critical_risks", []))
        warnings = _dict_items(readiness.get("warnings", []))
        confidence_value = readiness.get("confidence_score")
        last_24_hours = (
            SignalService._build_last_24_hours(
                session=session,
                release_id=release.release_id,
                latest_snapshot=snapshot,
            )
            if snapshot is not None
            else {
                "as_of": None,
                "baseline_at": None,
                "has_baseline": False,
                "items": [],
            }
        )
        outlook = SignalService._build_release_outlook(
            release_date=release.release_date,
            latest_snapshot=snapshot,
            final_signal=(
                str(readiness["signal"])
                if readiness.get("signal")
                in {"GREEN", "YELLOW", "RED", "INCONCLUSIVE"}
                else None
            ),
            confidence_score=(
                float(confidence_value)
                if isinstance(confidence_value, int | float)
                else None
            ),
            release_gates=release_gates,
            critical_risks=critical_risks,
            warnings=warnings,
            last_24_hours=last_24_hours,
        )
        return _read_only_mapping(outlook)

    def _prepare_risk_aging_evidence(
        self,
        *,
        session: Session,
        release: Release,
        snapshot: MetricSnapshot | None,
    ) -> Mapping[str, object]:
        if snapshot is None:
            return _read_only_mapping({})
        signal = SignalRepository.get_signal_for_snapshot(
            session=session,
            release_id=release.release_id,
            metric_snapshot_id=snapshot.id,
            ruleset_version=snapshot.ruleset_version,
        )
        evidence = signal.risk_aging_evidence if signal and signal.ruleset_version > 0 else {}
        return _read_only_mapping(evidence)

    def _prepare_portfolio(
        self,
        *,
        session: Session,
        project_key: str,
    ) -> PreparedPortfolioData:
        releases, release_count = ReleaseRepository.list_releases(
            session=session,
            project_key=project_key,
            skip=0,
            limit=1000,
        )
        sprints, sprint_count = SprintRepository.list_sprints(
            session=session,
            project_key=project_key,
            skip=0,
            limit=1000,
        )
        active_release_count = sum(
            1
            for item in releases
            if (item.status or "").casefold() in {"active", "unreleased"}
        )
        active_sprint_count = sum(
            1 for item in sprints if item.state.casefold() == "active"
        )
        computed_release_count = sum(
            1
            for item in releases
            if MetricRepository.get_latest_snapshot(
                session=session,
                release_id=item.release_id,
            )
            is not None
        )
        return PreparedPortfolioData(
            project_key=project_key,
            release_count=release_count,
            active_release_count=active_release_count,
            computed_release_count=computed_release_count,
            sprint_count=sprint_count,
            active_sprint_count=active_sprint_count,
        )


def stored_metric_availability(
    snapshot: MetricSnapshot | SprintMetricSnapshot | None,
) -> MetricAvailability | None:
    stored_availability = (
        (snapshot.calculation_provenance or {}).get("availability")
        if snapshot is not None and snapshot.ruleset_version > 0
        else None
    )
    if isinstance(stored_availability, dict):
        return MetricAvailability.model_validate(stored_availability)
    return None


def _release_metric_availability(
    *,
    session: Session,
    release_id: str,
    snapshot: MetricSnapshot | None,
) -> MetricAvailability:
    stored_availability = stored_metric_availability(snapshot)
    if stored_availability is not None:
        return stored_availability
    return MetricAvailabilityService.build_release_availability(
        session=session,
        release_id=release_id,
        field_mapper=JiraFieldMapper(get_settings()),
    )


def _prepare_release_comparison(
    snapshots: tuple[MetricSnapshot, ...],
) -> PreparedSnapshotComparison | None:
    if (
        len(snapshots) < 2
        or snapshots[-1].ruleset_version != snapshots[-2].ruleset_version
        or snapshots[-1].ruleset_version == 0
    ):
        return None
    comparison = SnapshotComparisonService.compare_release_snapshots(
        current_snapshot=snapshots[-1],
        previous_snapshot=snapshots[-2],
    )
    return PreparedSnapshotComparison(
        confidence_delta=comparison.confidence_delta,
        primary_driver=SnapshotComparisonService.primary_driver(comparison),
    )


def _prepare_sprint_comparison(
    snapshots: tuple[SprintMetricSnapshot, ...],
) -> PreparedSnapshotComparison | None:
    if (
        len(snapshots) < 2
        or snapshots[-1].ruleset_version != snapshots[-2].ruleset_version
    ):
        return None
    comparison = SnapshotComparisonService.compare_sprint_snapshots(
        current_snapshot=snapshots[-1],
        previous_snapshot=snapshots[-2],
    )
    return PreparedSnapshotComparison(
        confidence_delta=comparison.confidence_delta,
        primary_driver=SnapshotComparisonService.primary_driver(comparison),
    )


def _sprint_confidence_available(snapshot: SprintMetricSnapshot | None) -> bool:
    return bool(
        snapshot
        and snapshot.delivery_confidence_status in {"PARTIAL", "COMPUTED"}
        and snapshot.delivery_confidence_score is not None
    )


def _read_only_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


def _read_about_documentation() -> str:
    for path in _about_documentation_paths():
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise ValueError("ABOUT.md documentation was not found")


def _about_documentation_paths() -> list[Path]:
    bundled_root = Path(getattr(sys, "_MEIPASS", ""))
    service_path = Path(__file__).resolve()
    return [
        bundled_root / "ABOUT.md",
        service_path.parents[3] / "ABOUT.md",
        Path.cwd() / "ABOUT.md",
        Path.cwd().parent / "ABOUT.md",
    ]


def application_version() -> str:
    try:
        return metadata.version("jira-release-signals-backend")
    except metadata.PackageNotFoundError:
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if pyproject.exists():
            with pyproject.open("rb") as handle:
                return str(tomllib.load(handle)["project"]["version"])
        return "0.0.0"
