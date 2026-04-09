from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.release_repository import ReleaseRepository
from app.repositories.signal_repository import SignalRepository
from app.schemas.signals import ReleaseSignalResponse

router = APIRouter(prefix="/releases", tags=["signals"])


@router.get("/{release_id}/signal", response_model=ReleaseSignalResponse)
def get_release_signal(
    release_id: str,
    session: Session = Depends(get_db_session),
) -> ReleaseSignalResponse:
    release = ReleaseRepository.get_release_by_id(session=session, release_id=release_id)
    if release is None:
        raise HTTPException(status_code=404, detail=f"Release '{release_id}' not found")

    signal_row = SignalRepository.get_latest_signal(session=session, release_id=release_id)
    if signal_row is None:
        return ReleaseSignalResponse(
            release_id=release_id,
            signal=None,
            reasons=[],
            updated_at=None,
        )

    return ReleaseSignalResponse(
        release_id=signal_row.release_id,
        signal=signal_row.signal,
        reasons=signal_row.reasons,
        updated_at=signal_row.updated_at,
    )
