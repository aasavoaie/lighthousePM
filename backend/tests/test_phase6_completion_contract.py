from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
UNIT_TEST_DOCS = REPOSITORY_ROOT / "UNIT_TEST_DOCS.md"
README = REPOSITORY_ROOT / "README.md"
AGENTS = REPOSITORY_ROOT / "AGENTS.md"
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"

REQUIRED_JOBS = (
    "backend-quality",
    "postgres-integration",
    "frontend",
    "desktop",
    "docker-security",
)
REQUIRED_MATRIX_COMMANDS = (
    "python scripts/compile_python_locks.py",
    "make quality",
    "make postgres-test",
    "npm run check:dependencies",
    "npm test",
    "npm run build",
    "npm run build:backend",
    "npm run smoke:backend",
    "make docker-test",
)
REQUIRED_COVERAGE = (
    "read-only API snapshots",
    "whole-backend Ruff",
    "application MyPy",
    "SQLite migrations",
    "PostgreSQL migration and application-startup acceptance",
    "component and accessibility tests",
    "Vite production build",
    "real packaged Windows backend build",
    "isolated runtime health",
    "repository hygiene and indexed line endings",
)
REPORTING_CATEGORIES = (
    "### Locally passed",
    "### Environment-dependent",
    "### CI-only or pending",
    "### Warnings",
)


def _completion_matrix() -> str:
    guide = UNIT_TEST_DOCS.read_text(encoding="utf-8")
    return guide.split("## Phase 6 completion matrix", maxsplit=1)[1].split(
        "## Security acceptance gate",
        maxsplit=1,
    )[0]


def test_completion_matrix_assigns_every_required_job_and_coverage_area() -> None:
    matrix = _completion_matrix()

    for job_name in REQUIRED_JOBS:
        assert matrix.count(f"| `{job_name}` |") == 1
    for command in REQUIRED_MATRIX_COMMANDS:
        assert f"`{command}`" in matrix
    for coverage in REQUIRED_COVERAGE:
        assert coverage in matrix


def test_completion_matrix_matches_implemented_ci_jobs_and_entry_points() -> None:
    matrix = _completion_matrix()
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    makefile = (REPOSITORY_ROOT / "backend" / "Makefile").read_text(encoding="utf-8")
    frontend_package = (REPOSITORY_ROOT / "frontend" / "package.json").read_text(
        encoding="utf-8"
    )
    desktop_package = (REPOSITORY_ROOT / "desktop" / "package.json").read_text(
        encoding="utf-8"
    )

    for job_name in REQUIRED_JOBS:
        assert f"  {job_name}:\n    name: {job_name}" in workflow
    for target in ("quality", "postgres-test", "docker-test"):
        assert f"\n{target}:" in makefile
    for script_name in ("check:dependencies", "test", "build"):
        assert f'"{script_name}":' in frontend_package
    for script_name in (
        "check:dependencies",
        "lint",
        "test:node",
        "build:backend",
        "smoke:backend",
    ):
        assert f'"{script_name}":' in desktop_package
    assert "if: always()" in matrix


def test_completion_reporting_preserves_evidence_categories_and_truthfulness() -> None:
    matrix = _completion_matrix()

    for category in REPORTING_CATEGORIES:
        assert matrix.count(category) == 1
    assert (
        "A gate must not be reported as passed unless its command actually ran and\n"
        "returned success."
    ) in matrix
    assert "Do not infer GitHub results" in matrix
    assert "frontend bundle-size warning" in matrix


def test_readme_and_agents_reference_the_same_completion_contract() -> None:
    readme = " ".join(README.read_text(encoding="utf-8").split())
    agents = " ".join(AGENTS.read_text(encoding="utf-8").split())

    assert "Phase 6 completion matrix and evidence-report template" in readme
    for category in (
        "locally passed",
        "environment-dependent",
        "CI-only or pending",
        "warning",
    ):
        assert category in readme
        assert category in agents
    for job_name in REQUIRED_JOBS:
        assert job_name in agents
    assert "A local equivalent does not prove its GitHub Actions job passed." in agents
