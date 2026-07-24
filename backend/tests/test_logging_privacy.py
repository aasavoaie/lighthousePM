import logging

from app.main import _configure_logging


def test_configured_logging_redacts_token_like_values(capsys) -> None:
    _configure_logging("INFO")
    logging.getLogger("privacy-test").warning(
        "sync failed api_token=log-secret authorization=BearerSecret password=hidden"
    )

    captured = capsys.readouterr()

    assert "log-secret" not in captured.err
    assert "BearerSecret" not in captured.err
    assert "hidden" not in captured.err
    assert "[REDACTED]" in captured.err


def test_configured_logging_redacts_opaque_effective_secret_values(capsys) -> None:
    _configure_logging("INFO", ("opaque-database-credential",))
    logging.getLogger("privacy-test").warning(
        "database connection failed with opaque-database-credential"
    )

    captured = capsys.readouterr()

    assert "opaque-database-credential" not in captured.err
    assert "[REDACTED]" in captured.err
