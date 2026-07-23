from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from scripts import update_api_contract_snapshots


def test_makefile_exposes_only_the_explicit_contract_update_command() -> None:
    makefile = (update_api_contract_snapshots.BACKEND_DIR / "Makefile").read_text(
        encoding="utf-8"
    )

    assert "api-contracts-update:" in makefile
    assert "$(PYTHON) scripts/update_api_contract_snapshots.py" in makefile
    assert "quality: lint typecheck dependency-check migration-check test" in makefile
    assert "quality: api-contracts-update" not in makefile


def test_verification_guide_documents_read_only_and_update_workflows() -> None:
    guide = (
        update_api_contract_snapshots.BACKEND_DIR.parent / "UNIT_TEST_DOCS.md"
    ).read_text(encoding="utf-8")

    assert "### Critical API snapshot workflow" in guide
    assert "make api-contracts-update" in guide
    assert "python scripts/update_api_contract_snapshots.py" in guide
    assert "Normal tests and CI always compare these files read-only." in guide
    assert "CI never runs the update command." in guide


def test_regeneration_runs_two_update_passes_then_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes: list[bool] = []
    stable_state = {"manifest.json": b'{"version": 1}\n'}

    monkeypatch.setattr(
        update_api_contract_snapshots,
        "_run_contract_tests",
        lambda *, update: modes.append(update),
    )
    monkeypatch.setattr(
        update_api_contract_snapshots,
        "_read_snapshot_state",
        lambda: stable_state,
    )

    update_api_contract_snapshots.regenerate_api_contract_snapshots()

    assert modes == [True, True, False]


def test_regeneration_rejects_nondeterministic_second_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes: list[bool] = []
    states = iter(
        [
            {"configuration/jira-redacted.json": b'{"is_complete": true}\n'},
            {"configuration/jira-redacted.json": b'{"is_complete": false}\n'},
        ]
    )

    monkeypatch.setattr(
        update_api_contract_snapshots,
        "_run_contract_tests",
        lambda *, update: modes.append(update),
    )
    monkeypatch.setattr(
        update_api_contract_snapshots,
        "_read_snapshot_state",
        lambda: next(states),
    )

    with pytest.raises(
        update_api_contract_snapshots.ContractRegenerationError,
        match="configuration/jira-redacted.json",
    ):
        update_api_contract_snapshots.regenerate_api_contract_snapshots()

    assert modes == [True, True]


@pytest.mark.parametrize(("update", "expected_value"), [(True, "1"), (False, None)])
def test_contract_test_subprocess_controls_update_mode_explicitly(
    monkeypatch: pytest.MonkeyPatch,
    update: bool,
    expected_value: str | None,
) -> None:
    captured_environment: dict[str, str] = {}

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert command[:3] == [sys.executable, "-m", "pytest"]
        assert cwd == update_api_contract_snapshots.BACKEND_DIR
        assert check is False
        captured_environment.update(env)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv(
        update_api_contract_snapshots.API_CONTRACT_UPDATE_ENV, "inherited"
    )
    monkeypatch.setattr(update_api_contract_snapshots.subprocess, "run", fake_run)

    update_api_contract_snapshots._run_contract_tests(update=update)

    assert (
        captured_environment.get(update_api_contract_snapshots.API_CONTRACT_UPDATE_ENV)
        == expected_value
    )
