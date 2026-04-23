"""Application errors shared across DocMolder modules."""

from __future__ import annotations


class AppError(RuntimeError):
    """Base class for readable application failures."""


class ConfigurationError(AppError):
    """Raised when required configuration is missing or inconsistent."""


class ExternalServiceError(AppError):
    """Raised when an external service fails in a readable way."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TelegramApiError(ExternalServiceError):
    """Raised for Telegram Bot API failures."""


class ProcessingError(AppError):
    """Raised for document-processing failures that should stay user-readable."""
