"""Errors a service raises when a request breaks a rule.

Each one carries a snake_case code, one sentence a person can read, and the HTTP
status the API answers with. The API turns it into
{"error": {"code": ..., "message": ..., "details": [...]}}.
"""

from __future__ import annotations

from typing import Any, ClassVar


class ServiceError(Exception):
    status: ClassVar[int] = 400

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: list[Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []
        self.headers = headers or {}


class BadRequest(ServiceError):
    status = 400


class NotAuthenticated(ServiceError):
    status = 401

    def __init__(self, message: str = "Log in to do this.") -> None:
        super().__init__("not_authenticated", message, headers={"WWW-Authenticate": "Bearer"})


class Forbidden(ServiceError):
    status = 403


class NotFound(ServiceError):
    status = 404


class Conflict(ServiceError):
    status = 409


class PayloadTooLarge(ServiceError):
    status = 413


class UnsupportedMediaType(ServiceError):
    status = 415


class Unprocessable(ServiceError):
    status = 422


class TooManyRequests(ServiceError):
    status = 429


class InternalError(ServiceError):
    status = 500


class Unavailable(ServiceError):
    status = 503
