"""Run the required PostgreSQL suite and reject empty or skipped coverage."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from collections.abc import Sequence

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.postgres_test_support import (  # noqa: E402 - script entry-point path above
    POSTGRES_ADMIN_URL_ENV,
    REQUIRE_POSTGRES_ENV,
    validate_postgres_admin_url,
)


POSTGRES_TEST_MODULES = (
    "tests/test_migration_upgrade_matrix.py",
    "tests/test_application_startup_acceptance.py",
)


class RequiredPostgresPlugin:
    def __init__(self) -> None:
        self.collected_nodeids: set[str] = set()
        self.skipped_nodeids: set[str] = set()

    def pytest_collection_modifyitems(self, items: Sequence[pytest.Item]) -> None:
        self.collected_nodeids = {
            item.nodeid for item in items if item.get_closest_marker("postgres") is not None
        }

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.nodeid in self.collected_nodeids and report.skipped:
            self.skipped_nodeids.add(report.nodeid)

    def completion_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.collected_nodeids:
            errors.append("PostgreSQL integration collected no postgres-marked tests.")
        if self.skipped_nodeids:
            skipped = ", ".join(sorted(self.skipped_nodeids))
            errors.append(f"Required PostgreSQL tests skipped: {skipped}")
        return errors

    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        errors = self.completion_errors()
        if not errors:
            return
        for error in errors:
            print(error, file=sys.stderr)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def _require_configuration(*, command_line_required: bool) -> str:
    if command_line_required:
        os.environ[REQUIRE_POSTGRES_ENV] = "1"
    if os.getenv(REQUIRE_POSTGRES_ENV) != "1":
        raise RuntimeError(
            f"Set {REQUIRE_POSTGRES_ENV}=1 or pass --required to run the required gate."
        )

    admin_url = os.getenv(POSTGRES_ADMIN_URL_ENV, "").strip()
    if not admin_url:
        raise RuntimeError(f"{POSTGRES_ADMIN_URL_ENV} is required for the PostgreSQL gate.")
    validate_postgres_admin_url(admin_url)
    return admin_url


def _verify_admin_connection(admin_url: str) -> None:
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
    except (AssertionError, SQLAlchemyError) as exc:
        raise RuntimeError(
            "PostgreSQL administrative connection is unavailable or invalid."
        ) from exc
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--required",
        action="store_true",
        help=f"set {REQUIRE_POSTGRES_ENV}=1 for this run",
    )
    args = parser.parse_args()
    try:
        admin_url = _require_configuration(command_line_required=args.required)
        _verify_admin_connection(admin_url)
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    plugin = RequiredPostgresPlugin()
    exit_code = pytest.main(
        [*POSTGRES_TEST_MODULES, "-m", "postgres", "-q"],
        plugins=[plugin],
    )
    raise SystemExit(int(exit_code))


if __name__ == "__main__":
    main()
