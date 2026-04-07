from app.config import Settings, get_settings


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.app_name == "Jira Release Signals"
    assert settings.app_env == "dev"
    assert settings.app_port == 8000
    assert "://" in settings.database_url
    assert settings.database_echo is False
    assert settings.database_pool_size == 5
    assert settings.database_max_overflow == 10


def test_get_settings_cache() -> None:
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
