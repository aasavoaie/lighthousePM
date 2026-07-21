from app.db.migrations import migrate_database
from app.db.session import engine


def init_db() -> None:
    """Migrate the configured database before application use."""
    migrate_database(engine)
