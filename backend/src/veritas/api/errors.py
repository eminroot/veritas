"""One error format for every response.

    {"error": {"code": "snake_case", "message": "One sentence a person can read.", "details": []}}

Clients switch on `code` and can show `message` as it is. For invalid input each
detail is {"path": "body.phone", "message": "..."}, worded like Passport problems.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from veritas.passport.errors import describe, format_path
from veritas.services.errors import ServiceError

logger = logging.getLogger("veritas.api")


class ErrorBody(BaseModel):
    code: str = Field(examples=["not_found"])
    message: str = Field(examples=["There is nothing at this address."])
    details: list[Any] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorBody


_HTTP_ERRORS: dict[int, tuple[str, str]] = {
    400: ("bad_request", "The request could not be understood."),
    401: ("not_authenticated", "Log in to do this."),
    403: ("forbidden", "You are not allowed to do this."),
    404: ("not_found", "There is nothing at this address."),
    405: ("method_not_allowed", "This address does not accept that method."),
    409: ("conflict", "This clashes with something that is already saved."),
    413: ("payload_too_large", "The request is too large."),
    415: ("unsupported_media_type", "This type of content is not accepted here."),
    422: ("invalid_request", "Some fields are missing or not valid."),
    429: ("too_many_requests", "Too many requests. Try again later."),
    500: ("internal_error", "Something went wrong on our side."),
    503: ("unavailable", "The service is not available right now."),
}


def error_response(
    status: int,
    code: str,
    message: str,
    details: Sequence[Any] = (),
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": list(details)}}
    return JSONResponse(body, status_code=status, headers=dict(headers or {}))


async def _service_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServiceError)
    return error_response(exc.status, exc.code, exc.message, exc.details, exc.headers)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = []
    for error in exc.errors():
        if error["type"] == "json_invalid":
            detail = {"path": "body", "message": "is not valid JSON"}
        else:
            detail = {"path": format_path(error["loc"]), "message": describe(error)}
        if detail not in details:
            details.append(detail)
    code, message = _HTTP_ERRORS[422]
    return error_response(422, code, message, details)


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    # Only the framework raises these (unknown routes, wrong methods, body limits),
    # so our own wording replaces Starlette's.
    assert isinstance(exc, StarletteHTTPException)
    code, message = _HTTP_ERRORS.get(exc.status_code, (f"http_{exc.status_code}", str(exc.detail)))
    return error_response(exc.status_code, code, message, headers=exc.headers)


async def _integrity_error(request: Request, exc: Exception) -> JSONResponse:
    # Checks in the services catch these first; this is a race between two requests.
    logger.warning("integrity error on %s %s: %s", request.method, request.url.path, exc)
    code, message = _HTTP_ERRORS[409]
    return error_response(409, code, message)


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    code, message = _HTTP_ERRORS[500]
    return error_response(500, code, message)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, _service_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(IntegrityError, _integrity_error)
    app.add_exception_handler(Exception, _unexpected_error)
