from app.config import Settings, get_settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_name == "Jira Release Signals"
    assert settings.app_env == "dev"
    assert settings.app_port == 8000
    assert "://" in settings.database_url
    assert settings.database_echo is False
    assert settings.database_pool_size == 5
    assert settings.database_max_overflow == 10
    assert settings.lighthouse_api_token == ""
    assert settings.jira_sync_enabled is False
    assert settings.jira_sync_interval_seconds == 0
    assert settings.jira_field_severity == "priority"
    assert settings.jira_field_release == "fixVersions"


def test_get_settings_cache() -> None:
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second


def test_validate_startup_settings_fails_when_required_values_missing() -> None:
    settings = Settings(
        _env_file=None,
        jira_sync_enabled=True,
        jira_base_url="",
        jira_user_email="",
        jira_api_token="",
        jira_project_key="",
        jira_field_severity="",
        jira_field_release="",
        jira_changelog_fix_version_fields="",
    )

    try:
        settings.validate_startup_settings()
        assert False, "Expected ValueError for missing required startup settings"
    except ValueError as exc:
        assert "Missing required Jira startup settings" in str(exc)


def test_validate_startup_settings_skips_validation_when_sync_disabled() -> None:
    settings = Settings(
        _env_file=None,
        jira_sync_enabled=False,
        jira_base_url="",
        jira_user_email="",
        jira_api_token="",
        jira_project_key="",
    )

    settings.validate_startup_settings()
