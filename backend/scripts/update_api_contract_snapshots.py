from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
API_CONTRACT_ROOT = BACKEND_DIR / "tests" / "contracts" / "api"
API_CONTRACT_UPDATE_ENV = "LIGHTHOUSE_UPDATE_API_CONTRACT_SNAPSHOTS"
CONTRACT_TEST_MODULES = (
    "tests/test_api_contract_snapshots.py",
    "tests/test_release_api_contract_snapshots.py",
    "tests/test_sprint_api_contract_snapshots.py",
    "tests/test_configuration_sync_api_contract_snapshots.py",
)


class ContractRegenerationError(RuntimeError):
    """Raised when deterministic contract regeneration cannot be completed."""


def _run_contract_tests(*, update: bool) -> None:
    environment = os.environ.copy()
    if update:
        environment[API_CONTRACT_UPDATE_ENV] = "1"
    else:
        environment.pop(API_CONTRACT_UPDATE_ENV, None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", *CONTRACT_TEST_MODULES, "-q"],
        cwd=BACKEND_DIR,
        env=environment,
        check=False,
    )
    if result.returncode:
        mode = "regeneration" if update else "read-only verification"
        raise ContractRegenerationError(
            f"API contract {mode} failed with exit code {result.returncode}."
        )


def _read_snapshot_state() -> dict[str, bytes]:
    state = {
        path.relative_to(API_CONTRACT_ROOT).as_posix(): path.read_bytes()
        for path in sorted(API_CONTRACT_ROOT.rglob("*.json"))
    }
    if not state:
        raise ContractRegenerationError("No API contract JSON files were found.")
    return state


def _changed_paths(
    first: dict[str, bytes],
    second: dict[str, bytes],
) -> list[str]:
    paths = set(first) | set(second)
    return sorted(path for path in paths if first.get(path) != second.get(path))


def regenerate_api_contract_snapshots() -> None:
    _run_contract_tests(update=True)
    first_state = _read_snapshot_state()

    _run_contract_tests(update=True)
    second_state = _read_snapshot_state()
    changed_paths = _changed_paths(first_state, second_state)
    if changed_paths:
        joined_paths = ", ".join(changed_paths)
        raise ContractRegenerationError(
            "API contract regeneration is nondeterministic; the second pass changed: "
            f"{joined_paths}"
        )

    _run_contract_tests(update=False)


def main() -> int:
    try:
        regenerate_api_contract_snapshots()
    except ContractRegenerationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "API contracts regenerated deterministically and verified read-only. "
        "Review the resulting diff."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
