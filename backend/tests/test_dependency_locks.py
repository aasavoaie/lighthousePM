from __future__ import annotations

import re
import tomllib
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
REQUIREMENTS_DIR = BACKEND_DIR / "requirements"
LOCK_NAMES = {
    "linux-dev.lock",
    "linux-runtime.lock",
    "windows-dev.lock",
}
PIN_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\]+)", re.MULTILINE)
DEPENDENCY_NAME_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def _normalized_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _declared_names(dependencies: list[str]) -> set[str]:
    names: set[str] = set()
    for dependency in dependencies:
        match = DEPENDENCY_NAME_PATTERN.match(dependency)
        assert match is not None, f"Unable to parse dependency: {dependency}"
        names.add(_normalized_name(match.group(1)))
    return names


def _lock_packages(path: Path) -> set[str]:
    return {
        _normalized_name(match.group(1))
        for match in PIN_PATTERN.finditer(path.read_text(encoding="utf-8"))
    }


def test_platform_lock_set_and_pins_are_complete() -> None:
    lock_paths = sorted(REQUIREMENTS_DIR.glob("*.lock"))
    assert {path.name for path in lock_paths} == LOCK_NAMES

    for path in lock_paths:
        text = path.read_text(encoding="utf-8")
        matches = list(PIN_PATTERN.finditer(text))
        assert matches, f"No exact pins found in {path.name}"
        assert "C:\\" not in text
        assert "/mnt/" not in text
        for index, match in enumerate(matches):
            block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            assert "--hash=sha256:" in text[match.end() : block_end], (
                f"{match.group(1)} has no hash in {path.name}"
            )


def test_locks_cover_declared_runtime_and_development_dependencies() -> None:
    with (BACKEND_DIR / "pyproject.toml").open("rb") as pyproject_file:
        project = tomllib.load(pyproject_file)["project"]

    runtime_names = _declared_names(project["dependencies"])
    dev_names = _declared_names(project["optional-dependencies"]["dev"])
    linux_runtime = _lock_packages(REQUIREMENTS_DIR / "linux-runtime.lock")
    linux_dev = _lock_packages(REQUIREMENTS_DIR / "linux-dev.lock")
    windows_dev = _lock_packages(REQUIREMENTS_DIR / "windows-dev.lock")

    assert runtime_names <= linux_runtime
    assert runtime_names <= linux_dev
    assert runtime_names <= windows_dev
    assert dev_names.isdisjoint(linux_runtime)
    assert runtime_names | dev_names <= linux_dev
    assert runtime_names | dev_names <= windows_dev


def test_platform_specific_dependencies_do_not_leak_between_locks() -> None:
    linux_dev = _lock_packages(REQUIREMENTS_DIR / "linux-dev.lock")
    windows_dev = _lock_packages(REQUIREMENTS_DIR / "windows-dev.lock")

    assert "uvloop" in linux_dev
    assert "uvloop" not in windows_dev
    assert {"pefile", "pywin32-ctypes"} <= windows_dev
    assert {"pefile", "pywin32-ctypes"}.isdisjoint(linux_dev)


def test_dockerfile_installs_the_hashed_linux_runtime_lock() -> None:
    dockerfile = (BACKEND_DIR / "Dockerfile").read_text(encoding="utf-8")

    assert "requirements/linux-runtime.lock" in dockerfile
    assert "--require-hashes" in dockerfile
    assert "--no-deps --no-build-isolation ." in dockerfile
    assert "python -m pip check" in dockerfile
    assert "pip install --no-cache-dir --upgrade pip" not in dockerfile
    assert dockerfile.index("--require-hashes") < dockerfile.index("COPY app /app/app")
