from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_has_approved_global_controls() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "branches:\n      - main" in workflow
    assert "workflow_dispatch:" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "uses: actions/checkout@v7" in workflow
    assert "persist-credentials: false" in workflow
    assert "${{ secrets." not in workflow


def test_backend_job_uses_locked_quality_and_read_only_contract_gates() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    backend_job = workflow.split("  backend:\n", maxsplit=1)[1].split(
        "  desktop:\n", maxsplit=1
    )[0]

    assert "    name: backend" in backend_job
    assert "runs-on: ubuntu-latest" in backend_job
    assert "uses: actions/checkout@v7" in backend_job
    assert "persist-credentials: false" in backend_job
    assert "uses: actions/setup-python@v6" in backend_job
    assert 'python-version: "3.11"' in backend_job
    assert "cache-dependency-path: backend/requirements/linux-dev.lock" in backend_job
    assert "pip install --require-hashes -r requirements/linux-dev.lock" in backend_job
    assert "pip install --no-deps --no-build-isolation -e ." in backend_job
    assert "python -m pip check" in backend_job
    assert "working-directory: backend" in backend_job
    assert "name: Run backend quality gates and API contracts read-only" in backend_job
    assert "make quality" in backend_job
    assert (
        "python scripts/check_repository_hygiene.py --verification-clean" in backend_job
    )
    assert "api-contracts-update" not in backend_job
    assert "update_api_contract_snapshots.py" not in backend_job
    assert "LIGHTHOUSE_UPDATE_API_CONTRACT_SNAPSHOTS" not in backend_job


def test_postgres_integration_job_is_required_and_ephemeral() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    postgres_job = workflow.split("  postgres-integration:\n", maxsplit=1)[1]

    assert "  postgres-integration:\n    name: postgres-integration" in workflow
    assert "image: postgres:14" in workflow
    assert 'LIGHTHOUSE_REQUIRE_POSTGRES_INTEGRATION: "1"' in workflow
    assert "MIGRATION_TEST_POSTGRES_ADMIN_URL:" in workflow
    assert "synthetic-postgres-ci" in workflow
    assert "pg_isready -U postgres -d postgres" in workflow
    assert "volumes:" not in workflow
    assert "uses: actions/setup-python@v6" in workflow
    assert 'python-version: "3.11"' in workflow
    assert "pip install --require-hashes -r requirements/linux-dev.lock" in workflow
    assert "pip install --no-deps --no-build-isolation -e ." in workflow
    assert "python -m pip check" in workflow
    assert "python scripts/run_postgres_integration.py" in postgres_job
    assert (
        "python scripts/check_repository_hygiene.py --verification-clean"
        in postgres_job
    )


def test_frontend_job_uses_locked_isolated_test_and_build_gates() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    frontend_job = workflow.split("  frontend:\n", maxsplit=1)[1].split(
        "  postgres-integration:\n", maxsplit=1
    )[0]

    assert "    name: frontend" in frontend_job
    assert "runs-on: ubuntu-latest" in frontend_job
    assert "uses: actions/checkout@v7" in frontend_job
    assert "persist-credentials: false" in frontend_job
    assert "uses: actions/setup-node@v6" in frontend_job
    assert "uses: actions/setup-python@v6" in frontend_job
    assert 'node-version: "22"' in frontend_job
    assert "cache: npm" in frontend_job
    assert "cache-dependency-path: frontend/package-lock.json" in frontend_job
    assert "working-directory: frontend" in frontend_job
    assert "run: npm ci" in frontend_job
    assert "run: npm run check:dependencies" in frontend_job
    assert "name: Run frontend logic and component tests" in frontend_job
    assert "run: npm test" in frontend_job
    assert "run: npm run build" in frontend_job
    assert (
        "python backend/scripts/check_repository_hygiene.py --verification-clean"
        in frontend_job
    )
    assert "npm install" not in frontend_job
    assert "LIGHTHOUSE_" not in frontend_job
    assert "JIRA_" not in frontend_job

    assert frontend_job.index("run: npm ci") < frontend_job.index("run: npm test")
    assert frontend_job.index("run: npm test") < frontend_job.index(
        "run: npm run build"
    )


def test_desktop_job_builds_and_smokes_the_real_windows_backend() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    desktop_job = workflow.split("  desktop:\n", maxsplit=1)[1].split(
        "  frontend:\n", maxsplit=1
    )[0]

    assert "    name: desktop" in desktop_job
    assert "runs-on: windows-latest" in desktop_job
    assert "LIGHTHOUSE_PYTHON: python" in desktop_job
    assert "uses: actions/checkout@v7" in desktop_job
    assert "persist-credentials: false" in desktop_job
    assert "uses: actions/setup-node@v6" in desktop_job
    assert 'node-version: "22"' in desktop_job
    assert "cache-dependency-path: desktop/package-lock.json" in desktop_job
    assert "uses: actions/setup-python@v6" in desktop_job
    assert 'python-version: "3.11"' in desktop_job
    assert "cache-dependency-path: backend/requirements/windows-dev.lock" in desktop_job
    assert (
        "pip install --require-hashes -r requirements/windows-dev.lock" in desktop_job
    )
    assert "pip install --no-deps --no-build-isolation -e ." in desktop_job
    assert "python -m pip check" in desktop_job
    assert "run: npm ci" in desktop_job
    assert "run: npm run check:dependencies" in desktop_job
    assert "name: Lint desktop sources and scripts" in desktop_job
    assert "run: npm run lint" in desktop_job
    assert "name: Run desktop Node tests" in desktop_job
    assert "run: npm run test:node" in desktop_job
    assert "name: Build packaged Windows backend" in desktop_job
    assert "run: npm run build:backend" in desktop_job
    assert "name: Smoke-test packaged Windows backend" in desktop_job
    assert "run: npm run smoke:backend" in desktop_job
    assert (
        "python backend/scripts/check_repository_hygiene.py --verification-clean"
        in desktop_job
    )
    assert "npm install" not in desktop_job
    assert "npm run build:frontend" not in desktop_job
    assert "npm run package" not in desktop_job
    assert "npm run make" not in desktop_job
    assert "electron-forge start" not in desktop_job
    assert "JIRA_" not in desktop_job

    ordered_commands = [
        "run: npm ci",
        "run: npm run lint",
        "run: npm run test:node",
        "run: npm run build:backend",
        "run: npm run smoke:backend",
    ]
    positions = [desktop_job.index(command) for command in ordered_commands]
    assert positions == sorted(positions)
