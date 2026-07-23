from __future__ import annotations

from pathlib import Path

from scripts import check_dependency_inventory as inventory


def _write_fixture(
    root: Path,
    *,
    source: str,
    runtime_dependencies: tuple[str, ...] = (),
    dev_dependencies: tuple[str, ...] = (),
) -> None:
    (root / "app").mkdir()
    (root / "app" / "main.py").write_text(source, encoding="utf-8")
    runtime_lines = ",\n".join(f'  "{name}>=1,<2"' for name in runtime_dependencies)
    dev_lines = ",\n".join(f'  "{name}>=1,<2"' for name in dev_dependencies)
    (root / "pyproject.toml").write_text(
        "\n".join(
            (
                "[project]",
                'name = "fixture"',
                'version = "0.0.0"',
                f"dependencies = [\n{runtime_lines}\n]",
                "[project.optional-dependencies]",
                f"dev = [\n{dev_lines}\n]",
            )
        ),
        encoding="utf-8",
    )


def _clear_configured_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(inventory, "NON_IMPORT_RUNTIME_DISTRIBUTIONS", set())
    monkeypatch.setattr(inventory, "NON_IMPORT_DEV_DISTRIBUTIONS", set())


def test_current_backend_dependency_inventory_passes() -> None:
    assert inventory.dependency_inventory_errors() == []


def test_inventory_accepts_declared_imports_and_ignores_stdlib_and_local_modules(
    tmp_path: Path, monkeypatch
) -> None:
    _write_fixture(
        tmp_path,
        source="import json\nfrom app import local_module\nimport third_party\n",
        runtime_dependencies=("third-party",),
    )
    monkeypatch.setattr(
        inventory, "MODULE_DISTRIBUTIONS", {"third_party": "third-party"}
    )
    _clear_configured_dependencies(monkeypatch)

    assert inventory.dependency_inventory_errors(tmp_path) == []


def test_inventory_rejects_undeclared_and_unknown_third_party_imports(
    tmp_path: Path, monkeypatch
) -> None:
    _write_fixture(tmp_path, source="import known_module\nimport unknown_module\n")
    monkeypatch.setattr(
        inventory, "MODULE_DISTRIBUTIONS", {"known_module": "known-package"}
    )
    _clear_configured_dependencies(monkeypatch)

    assert inventory.dependency_inventory_errors(tmp_path) == [
        "app/main.py: module 'known_module' requires undeclared runtime "
        "distribution 'known-package'",
        "app/main.py: unknown third-party module 'unknown_module'",
    ]


def test_inventory_requires_explicit_command_only_tools(
    tmp_path: Path, monkeypatch
) -> None:
    _write_fixture(tmp_path, source="import json\n")
    monkeypatch.setattr(inventory, "MODULE_DISTRIBUTIONS", {})
    monkeypatch.setattr(inventory, "NON_IMPORT_RUNTIME_DISTRIBUTIONS", set())
    monkeypatch.setattr(inventory, "NON_IMPORT_DEV_DISTRIBUTIONS", {"ruff"})

    assert inventory.dependency_inventory_errors(tmp_path) == [
        "pyproject.toml: configured test/build distribution 'ruff' is undeclared"
    ]
