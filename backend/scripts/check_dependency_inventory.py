"""Verify that maintained Python imports have explicit dependency declarations."""

from __future__ import annotations

import argparse
import ast
import re
import sys
import tomllib
from collections import defaultdict
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEPENDENCY_NAME_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
MODULE_DISTRIBUTIONS = {
    "PyInstaller": "pyinstaller",
    "alembic": "alembic",
    "apscheduler": "apscheduler",
    "dotenv": "python-dotenv",
    "fastapi": "fastapi",
    "httpx": "httpx",
    "psycopg": "psycopg",
    "pydantic": "pydantic",
    "pydantic_settings": "pydantic-settings",
    "pytest": "pytest",
    "sqlalchemy": "sqlalchemy",
    "starlette": "starlette",
    "uvicorn": "uvicorn",
}
NON_IMPORT_RUNTIME_DISTRIBUTIONS = {"psycopg", "uvicorn"}
NON_IMPORT_DEV_DISTRIBUTIONS = {"mypy", "pip-tools", "pytest-asyncio", "ruff"}
RUNTIME_DIRECTORIES = ("app", "alembic")
DEVELOPMENT_DIRECTORIES = ("tests", "scripts")
RUNTIME_FILES = ("desktop_entry.py", "seed.py")
DEVELOPMENT_FILES = ("lighthousepm_backend.spec",)


def _normalized_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _dependency_names(values: list[str]) -> set[str]:
    names: set[str] = set()
    for value in values:
        match = DEPENDENCY_NAME_PATTERN.match(value)
        if match is None:
            raise ValueError(f"Unable to parse dependency declaration: {value}")
        names.add(_normalized_name(match.group(1)))
    return names


def _source_files(root: Path) -> tuple[list[Path], set[Path]]:
    runtime_files = [
        path
        for directory in RUNTIME_DIRECTORIES
        for path in (root / directory).rglob("*.py")
    ]
    runtime_files.extend(root / filename for filename in RUNTIME_FILES)
    development_files = [
        path
        for directory in DEVELOPMENT_DIRECTORIES
        for path in (root / directory).rglob("*.py")
    ]
    development_files.extend(root / filename for filename in DEVELOPMENT_FILES)
    existing_runtime = {path.resolve() for path in runtime_files if path.is_file()}
    all_files = sorted(
        existing_runtime | {path.resolve() for path in development_files if path.is_file()}
    )
    return all_files, existing_runtime


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.partition(".")[0])
    return modules


def _local_modules(root: Path) -> set[str]:
    modules = {"app", "scripts", "tests"}
    modules.update(path.stem for path in root.glob("*.py"))
    return modules


def dependency_inventory_errors(root: Path = BACKEND_DIR) -> list[str]:
    with (root / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)
    project = pyproject["project"]
    runtime_declared = _dependency_names(project.get("dependencies", []))
    dev_declared = _dependency_names(
        project.get("optional-dependencies", {}).get("dev", [])
    )

    files, runtime_files = _source_files(root)
    local_modules = _local_modules(root)
    imported_distributions: dict[str, set[str]] = defaultdict(set)
    runtime_imported_distributions: set[str] = set()
    errors: list[str] = []

    for path in files:
        relative_path = path.relative_to(root.resolve()).as_posix()
        allowed = runtime_declared if path in runtime_files else runtime_declared | dev_declared
        for module in sorted(_imported_modules(path)):
            if module in sys.stdlib_module_names or module in local_modules:
                continue
            distribution = MODULE_DISTRIBUTIONS.get(module)
            if distribution is None:
                errors.append(f"{relative_path}: unknown third-party module '{module}'")
                continue
            normalized_distribution = _normalized_name(distribution)
            imported_distributions[normalized_distribution].add(relative_path)
            if path in runtime_files:
                runtime_imported_distributions.add(normalized_distribution)
            if normalized_distribution not in allowed:
                scope = "runtime" if path in runtime_files else "runtime or dev"
                errors.append(
                    f"{relative_path}: module '{module}' requires undeclared {scope} "
                    f"distribution '{normalized_distribution}'"
                )

    imported_names = set(imported_distributions)
    accepted_runtime = runtime_imported_distributions | NON_IMPORT_RUNTIME_DISTRIBUTIONS
    accepted_dev = imported_names | NON_IMPORT_DEV_DISTRIBUTIONS
    for distribution in sorted(runtime_declared - accepted_runtime):
        errors.append(
            f"pyproject.toml: runtime dependency '{distribution}' has no maintained "
            "import or configured runtime use"
        )
    for distribution in sorted(dev_declared - accepted_dev):
        errors.append(
            f"pyproject.toml: dev dependency '{distribution}' has no maintained "
            "import or configured test/build use"
        )
    for distribution in sorted(NON_IMPORT_RUNTIME_DISTRIBUTIONS - runtime_declared):
        errors.append(
            f"pyproject.toml: configured runtime distribution '{distribution}' is undeclared"
        )
    for distribution in sorted(NON_IMPORT_DEV_DISTRIBUTIONS - dev_declared):
        errors.append(
            f"pyproject.toml: configured test/build distribution '{distribution}' is undeclared"
        )
    return sorted(set(errors))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=BACKEND_DIR,
        help="backend root containing pyproject.toml",
    )
    args = parser.parse_args()
    errors = dependency_inventory_errors(args.root.resolve())
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        raise SystemExit(1)
    print("Backend dependency inventory passed.")


if __name__ == "__main__":
    main()
