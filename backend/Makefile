PYTHON ?= python
APP_MODULE ?= app.main:app

.PHONY: help install install-dev locks locks-upgrade run test api-contracts-update postgres-test lint format typecheck dependency-check migration-check hygiene-check quality db-upgrade seed

help:
	@echo "Available targets:"
	@echo "  install      Install runtime dependencies"
	@echo "  install-dev  Install runtime + dev dependencies"
	@echo "  locks        Regenerate Python 3.11 locks, preserving pins"
	@echo "  locks-upgrade  Upgrade compatible pins for this platform"
	@echo "  run          Start FastAPI dev server"
	@echo "  test         Run normal backend tests (excluding PostgreSQL and Docker)"
	@echo "  api-contracts-update  Regenerate deterministic API contract snapshots"
	@echo "  postgres-test  Run required PostgreSQL integration acceptance"
	@echo "  lint         Run whole-backend Ruff checks"
	@echo "  format       Format code with Ruff"
	@echo "  typecheck    Run MyPy type checking"
	@echo "  dependency-check  Verify direct imports and installed packages"
	@echo "  migration-check  Verify SQLite migrations and startup upgrades"
	@echo "  hygiene-check  Verify repository artifacts and policies"
	@echo "  quality      Run lint, typecheck, dependencies, migrations, hygiene, and tests"
	@echo "  db-upgrade   Apply Alembic migrations"
	@echo "  seed         Insert sample data"

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

locks:
	$(PYTHON) scripts/compile_python_locks.py

locks-upgrade:
	$(PYTHON) scripts/compile_python_locks.py --upgrade

run:
	uvicorn $(APP_MODULE) --reload --port 8000

test:
	$(PYTHON) -m pytest tests -m "not postgres and not docker" -q

api-contracts-update:
	$(PYTHON) scripts/update_api_contract_snapshots.py

postgres-test:
	$(PYTHON) scripts/run_postgres_integration.py --required

lint:
	$(PYTHON) -m ruff check app tests alembic scripts desktop_entry.py seed.py

format:
	$(PYTHON) -m ruff format app tests alembic scripts desktop_entry.py seed.py

typecheck:
	$(PYTHON) -m mypy app

dependency-check:
	$(PYTHON) scripts/check_dependency_inventory.py
	$(PYTHON) -m pip check

migration-check:
	$(PYTHON) -m pytest tests/test_db.py tests/test_migration_upgrade_matrix.py tests/test_application_startup_acceptance.py -m "not postgres and not docker" -q

hygiene-check:
	$(PYTHON) scripts/check_repository_hygiene.py

quality: lint typecheck dependency-check migration-check hygiene-check test

db-upgrade:
	alembic upgrade head

seed:
	$(PYTHON) seed.py
