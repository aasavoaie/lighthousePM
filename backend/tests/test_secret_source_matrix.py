from pathlib import Path

import pytest

from app.config import MAX_SECRET_FILE_BYTES, Settings


SECRET_SETTINGS = (
    (
        "lighthouse_api_token",
        "lighthouse_api_token_file",
        "effective_lighthouse_api_token",
        "LIGHTHOUSE_API_TOKEN_FILE",
    ),
    (
        "jira_api_token",
        "jira_api_token_file",
        "effective_jira_api_token",
        "JIRA_API_TOKEN_FILE",
    ),
    (
        "postgres_password",
        "postgres_password_file",
        "effective_postgres_password",
        "POSTGRES_PASSWORD_FILE",
    ),
)


@pytest.mark.parametrize(
    "direct_field,file_field,effective_property,file_setting",
    SECRET_SETTINGS,
    ids=("api-token", "jira-token", "postgres-password"),
)
def test_direct_and_file_secret_sources_preserve_opaque_values(
    tmp_path: Path,
    direct_field: str,
    file_field: str,
    effective_property: str,
    file_setting: str,
) -> None:
    direct_settings = Settings(_env_file=None, **{direct_field: " direct secret "})
    assert getattr(direct_settings, effective_property) == " direct secret "

    secret_file = tmp_path / file_setting.casefold()
    secret_file.write_bytes(b" file secret \r\n")
    file_settings = Settings(_env_file=None, **{file_field: str(secret_file)})
    assert getattr(file_settings, effective_property) == " file secret "


@pytest.mark.parametrize(
    "direct_field,file_field,effective_property,file_setting",
    SECRET_SETTINGS,
    ids=("api-token", "jira-token", "postgres-password"),
)
def test_conflicting_secret_sources_fail_without_revealing_values(
    tmp_path: Path,
    direct_field: str,
    file_field: str,
    effective_property: str,
    file_setting: str,
) -> None:
    secret_file = tmp_path / file_setting.casefold()
    secret_file.write_text("file-secret-value", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        **{direct_field: "direct-secret-value", file_field: str(secret_file)},
    )

    with pytest.raises(ValueError, match="cannot both be configured") as exc_info:
        getattr(settings, effective_property)

    error = str(exc_info.value)
    assert "direct-secret-value" not in error
    assert "file-secret-value" not in error
    assert str(secret_file) not in error


@pytest.mark.parametrize(
    "direct_field,file_field,effective_property,file_setting",
    SECRET_SETTINGS,
    ids=("api-token", "jira-token", "postgres-password"),
)
@pytest.mark.parametrize(
    "contents",
    (b"", b" \n", b"x" * (MAX_SECRET_FILE_BYTES + 1), b"\xff"),
    ids=("empty", "whitespace", "oversized", "invalid-utf8"),
)
def test_invalid_secret_files_fail_closed_without_exposing_path_or_content(
    tmp_path: Path,
    direct_field: str,
    file_field: str,
    effective_property: str,
    file_setting: str,
    contents: bytes,
) -> None:
    secret_file = tmp_path / f"private-{file_setting.casefold()}"
    secret_file.write_bytes(contents)
    settings = Settings(_env_file=None, **{file_field: str(secret_file)})

    with pytest.raises(ValueError, match=file_setting) as exc_info:
        getattr(settings, effective_property)

    error = str(exc_info.value)
    assert str(secret_file) not in error
    if len(contents) >= 128:
        assert contents[:128].decode("utf-8", errors="ignore") not in error


@pytest.mark.parametrize(
    "direct_field,file_field,effective_property,file_setting",
    SECRET_SETTINGS,
    ids=("api-token", "jira-token", "postgres-password"),
)
def test_missing_directory_and_unreadable_secret_sources_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    direct_field: str,
    file_field: str,
    effective_property: str,
    file_setting: str,
) -> None:
    for invalid_path in (tmp_path / "missing", tmp_path):
        settings = Settings(_env_file=None, **{file_field: str(invalid_path)})
        with pytest.raises(ValueError, match=file_setting) as exc_info:
            getattr(settings, effective_property)
        assert str(invalid_path) not in str(exc_info.value)

    unreadable_file = tmp_path / f"unreadable-{file_setting.casefold()}"
    unreadable_file.write_text("opaque-secret", encoding="utf-8")
    original_read_text = Path.read_text

    def deny_selected_file(path: Path, *args, **kwargs) -> str:
        if path == unreadable_file:
            raise PermissionError("synthetic permission denial")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny_selected_file)
    settings = Settings(_env_file=None, **{file_field: str(unreadable_file)})
    with pytest.raises(ValueError, match=file_setting) as exc_info:
        getattr(settings, effective_property)
    assert str(unreadable_file) not in str(exc_info.value)
    assert "opaque-secret" not in str(exc_info.value)
