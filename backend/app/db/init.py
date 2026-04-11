from app.db.base import Base
from app.db.session import engine
from app.models import Issue, IssueHistory, MetricSnapshot, OperationalStatus, Release, ReleaseSignal


def init_db() -> None:
    """Create tables for local development when they do not exist."""
    _ = (Issue, IssueHistory, MetricSnapshot, OperationalStatus, Release, ReleaseSignal)
    Base.metadata.create_all(bind=engine)
