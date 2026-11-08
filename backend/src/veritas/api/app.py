"""The FastAPI application.

Run it with `uv run uvicorn veritas.api.app:create_app --factory`. Tests call
`create_app(settings)` with their own settings.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from veritas import __version__
from veritas.api.errors import ErrorResponse, install_error_handlers
from veritas.api.limits import BodyLimitMiddleware
from veritas.api.routes import (
    auth,
    charities,
    contractors,
    decisions,
    devices,
    documents,
    donations,
    evidence,
    health,
    officers,
    projects,
    receipts,
)
from veritas.chain.contracts import Deployment
from veritas.chain.runtime import Chain
from veritas.db.session import make_engine, make_session_factory
from veritas.payments.clients import BankClient, PspClient
from veritas.settings import Settings, get_settings
from veritas.storage import LocalStorage

TAGS = [
    {"name": "health", "description": "Liveness and readiness checks."},
    {"name": "auth", "description": "Login with a one-time code sent to a phone."},
    {"name": "account", "description": "The caller's own account."},
    {"name": "devices", "description": "Keys on users' phones, proven by signing a challenge."},
    {
        "name": "charities",
        "description": "Charity onboarding: details, KYB documents, review, members, signing key.",
    },
    {"name": "contractors", "description": "Contractors a charity pays, verified by Veritas."},
    {"name": "officers", "description": "Verification Officers that Passports can name."},
    {"name": "documents", "description": "Downloading KYB documents."},
    {
        "name": "projects",
        "description": "Passport drafts and their problems, publishing, and public project pages.",
    },
    {"name": "donations", "description": "Card donations and receipts with Merkle proofs."},
    {"name": "receipts", "description": "A donor's receipts, and moving one to a new key."},
    {"name": "evidence", "description": "Capture sessions, uploads, checks and anchoring."},
    {
        "name": "decisions",
        "description": "Officer decisions, donor votes, pledges, stopping a project and claims.",
    },
]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.otp_echo:
        _show_login_codes()

    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(
        title="Veritas API",
        version=__version__,
        description="Donations that move only when the work is proven.",
        openapi_tags=TAGS,
        lifespan=lifespan,
        responses={"4XX": {"model": ErrorResponse, "description": "The request was refused."}},
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.storage = LocalStorage(settings.storage_dir)
    app.state.psp = PspClient(
        httpx.Client(base_url=settings.psp_base_url, timeout=15),
        settings.psp_api_key.get_secret_value(),
    )
    app.state.bank = BankClient(
        httpx.Client(base_url=settings.bank_base_url, timeout=15),
        settings.bank_api_key.get_secret_value(),
    )
    app.state.chain = (
        Chain.connect(settings.chain_rpc_url, Deployment.load(settings.deployment_file))
        if settings.chain_enabled
        else None
    )

    app.add_middleware(BodyLimitMiddleware, max_file_bytes=settings.max_upload_bytes)
    install_error_handlers(app)
    routers = (
        health,
        auth,
        devices,
        charities,
        contractors,
        officers,
        documents,
        projects,
        donations,
        receipts,
        evidence,
        decisions,
    )
    for module in routers:
        app.include_router(module.router)
    return app


def _show_login_codes() -> None:
    """Make sure echoed login codes reach the console.

    Uvicorn sets up only its own loggers, so an INFO record from veritas.auth would
    otherwise be dropped. When something else already configured logging, leave it.
    """
    logger = logging.getLogger("veritas")
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)
    if not logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
        logger.addHandler(handler)
