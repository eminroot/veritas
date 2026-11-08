"""How big a request body may be, checked before anything reads it.

FastAPI reads and parses a whole body before it authenticates the caller, so one limit sized
for photo uploads on every route would let anyone make the API parse a half-gigabyte JSON
document. Bodies are small by default; only the routes that take files accept multipart bodies
as large as a file. A request over its limit gets the API's usual JSON error, 413
payload_too_large, whether it said its size up front or streamed past the limit.
"""

from __future__ import annotations

import re

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from veritas.api.errors import error_response

SMALL_BODY = 1024 * 1024
"""Every JSON body. The largest are a manifest and a Passport draft, each published as one
256 KiB block at most."""
MULTIPART_OVERHEAD = 1024 * 1024
FILE_ROUTES = re.compile(
    r"^/v1/(capture-sessions/[^/]+/items|charities/[^/]+/documents|contractors/[^/]+/documents)$"
)


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_file_bytes: int) -> None:
        self.app = app
        self.files = max_file_bytes + MULTIPART_OVERHEAD

    def limit(self, scope: Scope) -> int:
        headers = Headers(scope=scope)
        content_type = headers.get("content-type", "").strip().lower()
        multipart = content_type.startswith("multipart/form-data")
        return self.files if multipart and FILE_ROUTES.match(scope["path"]) else SMALL_BODY

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limit(scope)
        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            response = error_response(
                413,
                "payload_too_large",
                f"The request is larger than {limit // (1024 * 1024)} MB.",
            )
            await response(scope, receive, send)
            return
        received = 0

        async def receive_within_limit() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Raised inside the app, so its handler answers in the API's format.
                    raise HTTPException(413)
            return message

        await self.app(scope, receive_within_limit, send)
