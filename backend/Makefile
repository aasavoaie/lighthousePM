PYTHON ?= python
APP_MODULE ?= app.main:app

.PHONY: help install install-dev run test lint format typecheck db-upgrade seed

help:
	@echo "Available targets:"
	@echo "  install      Install runtime dependencies"
	@echo "  install-dev  Install runtime + dev dependencies"
	@echo "  run          Start FastAPI dev server"
	@echo "  test         Run backend tests"
	@echo "  lint         Run Ruff checks"
	@echo "  format       Format code with Ruff"
	@echo "  typecheck    Run MyPy type checking"
	@echo "  db-upgrade   Apply Alembic migrations"
	@echo "  seed         Insert sample data"

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e .
	$(PYTHON) -m pip install -r requirements-dev.txt

run:
	uvicorn $(APP_MODULE) --reload --port 8000

test:
	pytest tests/ -v --tb=short

lint:
	ruff check app tests

format:
	ruff format app tests

typecheck:
	mypy app

db-upgrade:
	alembic upgrade head

seed:
	$(PYTHON) seed.py
