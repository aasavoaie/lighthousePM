import logging
from time import perf_counter

from sqlalchemy.orm import Session

from app.repositories.release_repository import ReleaseRepository
from app.schemas.metrics import (
    RecomputeAllError,
    RecomputeAllMetricsResponse,
    RecomputeMetricsResponse,
)
from app.schemas.sprints import RecomputeSprintMetricsResponse
from app.services.analytics_service import AnalyticsService
from app.services.application_errors import ApplicationNotFoundError
from app.services.signal_service import SignalService
from app.utils.error_sanitizer import sanitize_error_detail


logger = logging.getLogger(__name__)


class MetricRecomputeService:
    """Coordinate metric mutations and their transaction boundaries."""

    def recompute_release(
        self,
        *,
        session: Session,
        release_id: str,
    ) -> RecomputeMetricsResponse:
        started_at = perf_counter()
        logger.info("release_recompute_started release_id=%s", release_id)
        try:
            snapshot = AnalyticsService().recompute_release_metrics(
                session=session,
                release_id=release_id,
            )
            SignalService().recompute_release_signal(
                session=session,
                release_id=release_id,
            )
            session.commit()
            logger.info(
                "release_recompute_completed release_id=%s elapsed_seconds=%.3f",
                release_id,
                perf_counter() - started_at,
            )
        except ValueError as exc:
            session.rollback()
            logger.warning("release_recompute_failed release_id=%s error=%s", release_id, exc)
            raise ApplicationNotFoundError(str(exc)) from exc
        return RecomputeMetricsResponse(
            release_id=snapshot.release_id,
            snapshot_at=snapshot.snapshot_at,
            ruleset_version=snapshot.ruleset_version,
            status="ok",
        )

    def recompute_all_releases(self, *, session: Session) -> RecomputeAllMetricsResponse:
        started_at = perf_counter()
        release_ids = ReleaseRepository.list_release_ids(session=session)
        errors: list[RecomputeAllError] = []
        recomputed_count = 0
        logger.info("release_recompute_all_started release_count=%d", len(release_ids))
        analytics_service = AnalyticsService()
        signal_service = SignalService()
        for release_id in release_ids:
            try:
                analytics_service.recompute_release_metrics(
                    session=session,
                    release_id=release_id,
                )
                signal_service.recompute_release_signal(
                    session=session,
                    release_id=release_id,
                )
                session.commit()
                recomputed_count += 1
            except Exception as exc:  # noqa: BLE001 - best-effort batch operation
                session.rollback()
                errors.append(
                    RecomputeAllError(
                        release_id=release_id,
                        reason=sanitize_error_detail(str(exc)),
                    )
                )
                logger.warning(
                    "release_recompute_all_item_failed release_id=%s error=%s",
                    release_id,
                    exc,
                )
        elapsed = perf_counter() - started_at
        logger.info(
            "release_recompute_all_completed release_count=%d recomputed=%d failed=%d "
            "elapsed_seconds=%.3f",
            len(release_ids),
            recomputed_count,
            len(errors),
            elapsed,
        )
        return RecomputeAllMetricsResponse(
            releases_total=len(release_ids),
            releases_recomputed=recomputed_count,
            releases_failed=len(errors),
            elapsed_seconds=round(elapsed, 3),
            errors=errors,
        )

    def recompute_sprint(
        self,
        *,
        session: Session,
        sprint_id: str,
    ) -> RecomputeSprintMetricsResponse:
        try:
            snapshot = AnalyticsService().recompute_sprint_metrics(
                session=session,
                sprint_id=sprint_id,
            )
            session.commit()
        except ValueError as exc:
            session.rollback()
            raise ApplicationNotFoundError(str(exc)) from exc
        return RecomputeSprintMetricsResponse(
            sprint_id=snapshot.sprint_id,
            snapshot_at=snapshot.snapshot_at,
            ruleset_version=snapshot.ruleset_version,
            status="ok",
        )
