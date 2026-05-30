import re


_SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(api[_-]?token\s*[=:]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(authorization\s*[=:]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(password\s*[=:]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(secret\s*[=:]\s*)([^\s,;]+)"),
]


def sanitize_error_detail(detail: str, max_length: int = 280) -> str:
    """Return a shortened error message with obvious secrets redacted."""
    sanitized = detail
    for pattern in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub(r"\1[REDACTED]", sanitized)
    sanitized = sanitized.strip()
    if len(sanitized) > max_length:
        return f"{sanitized[: max_length - 3]}..."
    return sanitized
