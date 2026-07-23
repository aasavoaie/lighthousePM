from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_docker_security as gate


BACKEND_ROOT = Path(__file__).resolve().parents[1]


class _FakeItem:
    def __init__(self, nodeid: str, *, docker: bool) -> None:
        self.nodeid = nodeid
        self._docker = docker

    def get_closest_marker(self, marker_name: str):
        if marker_name == "docker" and self._docker:
            return object()
        return None


def test_gate_requires_explicit_required_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(gate.REQUIRE_DOCKER_ENV, raising=False)
    with pytest.raises(RuntimeError, match=gate.REQUIRE_DOCKER_ENV):
        gate._require_mode(command_line_required=False)

    gate._require_mode(command_line_required=True)
    assert gate.os.environ[gate.REQUIRE_DOCKER_ENV] == "1"


def test_gate_runs_static_and_runtime_security_modules() -> None:
    assert gate.DOCKER_TEST_MODULES == (
        "tests/test_docker_security.py",
        "tests/test_docker_runtime_security.py",
    )


def test_make_target_invokes_the_required_runner() -> None:
    makefile = (BACKEND_ROOT / "Makefile").read_text(encoding="utf-8")

    assert (
        "\ndocker-test:\n"
        "\t$(PYTHON) scripts/run_docker_security.py --required\n" in makefile
    )


def test_required_plugin_rejects_zero_runtime_collection_and_skips() -> None:
    plugin = gate.RequiredDockerPlugin()
    assert plugin.completion_errors() == [
        "Docker security acceptance collected no docker-marked tests."
    ]

    plugin.pytest_collection_modifyitems(
        [
            _FakeItem("test_gate.py::test_runtime", docker=True),
            _FakeItem("test_gate.py::test_static", docker=False),
        ]  # type: ignore[arg-type]
    )
    plugin.pytest_runtest_logreport(
        SimpleNamespace(nodeid="test_gate.py::test_runtime", skipped=True)  # type: ignore[arg-type]
    )
    assert plugin.completion_errors() == [
        "Required Docker security tests skipped: test_gate.py::test_runtime"
    ]
