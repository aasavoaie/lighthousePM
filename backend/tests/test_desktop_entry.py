import os
from pathlib import Path

import pytest

from desktop_entry import _load_optional_env_file, _sqlite_url


def test_sqlite_url_uses_absolute_forward_slash_path(tmp_path: Path) -> None:
    database_path = tmp_path / "local data" / "lighthouse.db"

    database_url = _sqlite_url(database_path)

    assert database_url == f"sqlite+pysqlite:///{database_path.resolve().as_posix()}"


def test_optional_env_file_loads_values_without_overriding_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / "backend.env"
    env_file.write_text(
        "LIGHTHOUSE_TEST_EXISTING=FROM_FILE\nLIGHTHOUSE_TEST_NEW=FROM_FILE\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LIGHTHOUSE_TEST_EXISTING", "FROM_PROCESS")
    monkeypatch.delenv("LIGHTHOUSE_TEST_NEW", raising=False)

    _load_optional_env_file(env_file)

    assert os.environ["LIGHTHOUSE_TEST_EXISTING"] == "FROM_PROCESS"
    assert os.environ["LIGHTHOUSE_TEST_NEW"] == "FROM_FILE"
