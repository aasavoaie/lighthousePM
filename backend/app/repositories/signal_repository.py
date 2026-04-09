from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import ReleaseSignal


class SignalRepository:
    """Read/write queries for release signals.

    MVP policy: keep one current signal row per release (latest-only), updated
    in place on each recompute.
    """

    @staticmethod
    def get_latest_signal(session: Session, release_id: str) -> ReleaseSignal | None:
        query = (
            select(ReleaseSignal)
            .where(ReleaseSignal.release_id == release_id)
            .order_by(desc(ReleaseSignal.updated_at), desc(ReleaseSignal.id))
            .limit(1)
        )
        return session.scalar(query)

    @staticmethod
    def upsert_signal(
        session: Session,
        release_id: str,
        signal: str,
        reasons: list[str],
    ) -> ReleaseSignal:
        existing = SignalRepository.get_latest_signal(session=session, release_id=release_id)
        if existing is None:
            existing = ReleaseSignal(
                release_id=release_id,
                signal=signal,
                reasons=reasons,
            )
            session.add(existing)
            return existing

        existing.signal = signal
        existing.reasons = reasons
        return existing
