"""Run the required Docker security suite and reject empty or skipped coverage."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import os
import sys

import pytest


REQUIRE_DOCKER_ENV = "LIGHTHOUSE_REQUIRE_DOCKER_SECURITY"
DOCKER_TEST_MODULES = (
    "tests/test_docker_security.py",
    "tests/test_docker_runtime_security.py",
)


class RequiredDockerPlugin:
    def __init__(self) -> None:
        self.collected_nodeids: set[str] = set()
        self.skipped_nodeids: set[str] = set()

    def pytest_collection_modifyitems(self, items: Sequence[pytest.Item]) -> None:
        self.collected_nodeids = {
            item.nodeid
            for item in items
            if item.get_closest_marker("docker") is not None
        }

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.nodeid in self.collected_nodeids and report.skipped:
            self.skipped_nodeids.add(report.nodeid)

    def completion_errors(self) -> list[str]:
        errors: list[str] = []
        if not self.collected_nodeids:
            errors.append(
                "Docker security acceptance collected no docker-marked tests."
            )
        if self.skipped_nodeids:
            skipped = ", ".join(sorted(self.skipped_nodeids))
            errors.append(f"Required Docker security tests skipped: {skipped}")
        return errors

    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        errors = self.completion_errors()
        if not errors:
            return
        for error in errors:
            print(error, file=sys.stderr)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def _require_mode(*, command_line_required: bool) -> None:
    if command_line_required:
        os.environ[REQUIRE_DOCKER_ENV] = "1"
    if os.getenv(REQUIRE_DOCKER_ENV) != "1":
        raise RuntimeError(
            f"Set {REQUIRE_DOCKER_ENV}=1 or pass --required to run the required gate."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--required",
        action="store_true",
        help=f"set {REQUIRE_DOCKER_ENV}=1 for this run",
    )
    args = parser.parse_args()
    try:
        _require_mode(command_line_required=args.required)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    plugin = RequiredDockerPlugin()
    exit_code = pytest.main(
        [*DOCKER_TEST_MODULES, "-q"],
        plugins=[plugin],
    )
    raise SystemExit(int(exit_code))


if __name__ == "__main__":
    main()
