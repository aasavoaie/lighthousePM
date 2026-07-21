import asyncio

import pytest

import app.main as main_module


class _StartupSettings:
    def __init__(self, events: list[str], *, validation_error: Exception | None = None) -> None:
        self._events = events
        self._validation_error = validation_error

    def validate_startup_settings(self) -> None:
        self._events.append("validate")
        if self._validation_error is not None:
            raise self._validation_error


def _run_lifespan() -> list[str]:
    events: list[str] = []

    async def run() -> None:
        async with main_module.app_lifespan(main_module.app):
            events.append("ready")

    asyncio.run(run())
    return events


def test_startup_validates_migrates_and_starts_scheduler_before_readiness(monkeypatch) -> None:
    events: list[str] = []
    settings = _StartupSettings(events)

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "init_db", lambda: events.append("migrate"))
    monkeypatch.setattr(
        main_module,
        "start_scheduler",
        lambda actual_settings: events.append("scheduler_start")
        if actual_settings is settings
        else None,
    )
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: events.append("scheduler_stop"))

    async def run() -> None:
        async with main_module.app_lifespan(main_module.app):
            events.append("ready")

    asyncio.run(run())

    assert events == ["validate", "migrate", "scheduler_start", "ready", "scheduler_stop"]


def test_migration_failure_prevents_scheduler_and_readiness(monkeypatch) -> None:
    events: list[str] = []
    settings = _StartupSettings(events)

    def fail_migration() -> None:
        events.append("migrate")
        raise RuntimeError("migration failed")

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "init_db", fail_migration)
    monkeypatch.setattr(main_module, "start_scheduler", lambda _settings: events.append("scheduler_start"))
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: events.append("scheduler_stop"))

    with pytest.raises(RuntimeError, match="migration failed"):
        _run_lifespan()

    assert events == ["validate", "migrate"]


def test_configuration_failure_prevents_migration_scheduler_and_readiness(monkeypatch) -> None:
    events: list[str] = []
    settings = _StartupSettings(events, validation_error=RuntimeError("invalid configuration"))

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "init_db", lambda: events.append("migrate"))
    monkeypatch.setattr(main_module, "start_scheduler", lambda _settings: events.append("scheduler_start"))
    monkeypatch.setattr(main_module, "stop_scheduler", lambda: events.append("scheduler_stop"))

    with pytest.raises(RuntimeError, match="invalid configuration"):
        _run_lifespan()

    assert events == ["validate"]
