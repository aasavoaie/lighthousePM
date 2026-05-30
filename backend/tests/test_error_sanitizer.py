from app.utils.error_sanitizer import sanitize_error_detail


def test_sanitize_error_detail_redacts_sensitive_keys() -> None:
    raw = "Jira failed api_token=abcd1234 password=secret authorization=BearerABC"
    sanitized = sanitize_error_detail(raw)

    assert "abcd1234" not in sanitized
    assert "secret" not in sanitized
    assert "BearerABC" not in sanitized
    assert "[REDACTED]" in sanitized


def test_sanitize_error_detail_truncates_long_messages() -> None:
    raw = "x" * 400
    sanitized = sanitize_error_detail(raw, max_length=100)

    assert len(sanitized) == 100
    assert sanitized.endswith("...")
