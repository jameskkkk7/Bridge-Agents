"""Expected failures that map to HTTP statuses.

The base classes carry a status code and a stable error name so both the API
layer and library users can catch and map them consistently. The FastAPI
handlers live in the server application.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for failures that map to a known HTTP status."""

    status_code = 500
    error_name = "InternalError"

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class AuthError(AppError):
    """The caller could not be authenticated."""

    status_code = 401
    error_name = "AuthError"


class AccessDeniedError(AppError):
    """The authenticated caller is not allowed to perform the action."""

    status_code = 403
    error_name = "AccessDeniedError"


class NotFoundError(AppError):
    """The requested resource does not exist."""

    status_code = 404
    error_name = "NotFoundError"


class ValidationError(AppError):
    """The supplied input is not acceptable."""

    status_code = 422
    error_name = "ValidationError"


class ExternalServiceError(AppError):
    """A dependency outside this service failed."""

    status_code = 502
    error_name = "ExternalServiceError"


__all__ = [
    "AccessDeniedError",
    "AppError",
    "AuthError",
    "ExternalServiceError",
    "NotFoundError",
    "ValidationError",
]
