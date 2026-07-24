class ApplicationServiceError(Exception):
    """Base error for controlled application-service outcomes."""


class ApplicationNotFoundError(ApplicationServiceError):
    """Requested application resource does not exist."""


class ApplicationValidationError(ApplicationServiceError):
    """Application request values are internally inconsistent."""
