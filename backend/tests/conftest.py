"""Shared fixtures.

Database and API tests run against a real PostgreSQL with PostGIS. Set
VERITAS_TEST_DATABASE_URL to the server's `postgres` database, as a user that may
create databases. Each test session creates its own database there
(veritas_test_<8 hex>), migrates it with Alembic and drops it at the end. Tables
are emptied before every test. Without the variable, the tests that need a
database are skipped and everything else still runs.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from veritas.api.app import create_app
from veritas.api.deps import get_session
from veritas.core.identifiers import normalize_az_phone
from veritas.db.base import Base
from veritas.db.models import User
from veritas.db.session import make_engine, make_session_factory, session_scope
from veritas.settings import Settings

BACKEND = Path(__file__).resolve().parents[1]


def admin_database_url() -> str:
    url = os.environ.get("VERITAS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("needs PostgreSQL: set VERITAS_TEST_DATABASE_URL (see backend/README.md)")
    return url


def create_database(admin_url: str) -> str:
    """A new, empty database on the same server. Returns its URL."""
    name = f"veritas_test_{uuid.uuid4().hex[:8]}"
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine.dispose()
    return make_url(admin_url).set(database=name).render_as_string(hide_password=False)


def drop_database(admin_url: str, url: str) -> None:
    name = make_url(url).database
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    engine.dispose()


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["url"] = url
    config.attributes["configure_logging"] = False
    return config


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    admin_url = admin_database_url()
    url = create_database(admin_url)
    try:
        command.upgrade(alembic_config(url), "head")
        yield url
    finally:
        drop_database(admin_url, url)


@dataclass(frozen=True)
class ScratchDatabase:
    url: str
    alembic: Config


@pytest.fixture
def scratch_database() -> Iterator[ScratchDatabase]:
    """An empty database of its own, not migrated, dropped after the test."""
    admin_url = admin_database_url()
    url = create_database(admin_url)
    try:
        yield ScratchDatabase(url=url, alembic=alembic_config(url))
    finally:
        drop_database(admin_url, url)


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    engine = make_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def clean_db(engine: Engine) -> None:
    """Empty every table. DELETE is far quicker than TRUNCATE for a handful of rows.

    Triggers are off for this one transaction, so the rule that a published Passport
    is never deleted does not stand in the way of the cleanup. Tables a model defines
    but no migration has created yet are left to tests/db/test_migrations.py to report.
    """
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL session_replication_role = replica"))
        existing = set(
            connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in existing:
                connection.execute(table.delete())


@pytest.fixture
def db(engine: Engine, clean_db: None) -> Iterator[Session]:
    """A session for setting up and checking rows directly. Commit what the API should see."""
    with Session(engine) as session:
        yield session


@pytest.fixture(scope="session")
def settings(database_url: str, tmp_path_factory: pytest.TempPathFactory) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        database_url=database_url,
        storage_dir=tmp_path_factory.mktemp("storage"),
        otp_echo=True,
        secret_key=SecretStr("test-only-key-for-login-code-hmacs"),
    )


@pytest.fixture(scope="session")
def app(settings: Settings, engine: Engine) -> FastAPI:
    """The real app, sharing the test engine so tests and requests use one pool."""
    app = create_app(settings)
    factory = make_session_factory(engine)

    def shared_session() -> Iterator[Session]:
        yield from session_scope(factory)

    app.dependency_overrides[get_session] = shared_session
    return app


@pytest.fixture
def client(app: FastAPI, clean_db: None) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


class LoginCodes(logging.Handler):
    """Reads login codes from the log, the way a developer does with otp_echo on."""

    PATTERN = re.compile(r"Login code for (\+994\d{9}) is (\d{6})")

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.codes: dict[str, str] = {}

    def emit(self, record: logging.LogRecord) -> None:
        match = self.PATTERN.search(record.getMessage())
        if match:
            self.codes[match.group(1)] = match.group(2)

    def latest(self, phone: str) -> str:
        return self.codes[normalize_az_phone(phone)]


@pytest.fixture
def login_codes() -> Iterator[LoginCodes]:
    handler = LoginCodes()
    logger = logging.getLogger("veritas.auth")
    level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    yield handler
    logger.removeHandler(handler)
    logger.setLevel(level)


@dataclass(frozen=True)
class LoggedIn:
    user_id: uuid.UUID
    phone: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest.fixture
def login(client: TestClient, login_codes: LoginCodes) -> Callable[[str], LoggedIn]:
    """Log a phone in through the real OTP flow."""

    def log_in(phone: str) -> LoggedIn:
        response = client.post("/v1/auth/otp", json={"phone": phone})
        assert response.status_code == 202, response.text
        response = client.post(
            "/v1/auth/token", json={"phone": phone, "code": login_codes.latest(phone)}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        return LoggedIn(
            user_id=uuid.UUID(body["user"]["id"]),
            phone=body["user"]["phone"],
            token=body["access_token"],
        )

    return log_in


@pytest.fixture
def make_admin(db: Session) -> Callable[[LoggedIn], LoggedIn]:
    """Turn a logged-in user into a Veritas admin. There is no endpoint for that on purpose."""

    def promote(person: LoggedIn) -> LoggedIn:
        db.execute(update(User).where(User.id == person.user_id).values(is_admin=True))
        db.commit()
        return person

    return promote


@pytest.fixture
def admin(login: Callable[[str], LoggedIn], make_admin: Callable[[LoggedIn], LoggedIn]) -> LoggedIn:
    return make_admin(login("+994 50 000 00 01"))


# ---------------------------------------------------------------- a local chain

from chainkit import accounts as _accounts  # noqa: E402
from chainkit import anvil_binary, run_anvil  # noqa: E402
from veritas.chain.contracts import Contracts, Deployment, deploy_system  # noqa: E402
from veritas.chain.runtime import Chain  # noqa: E402


@pytest.fixture(scope="session")
def anvil_url() -> Iterator[str]:
    binary = anvil_binary()
    if not binary:
        pytest.skip("needs anvil: install Foundry or set VERITAS_ANVIL")
    with run_anvil(binary) as url:
        yield url


@pytest.fixture
def accounts():
    return _accounts()


@pytest.fixture(scope="session")
def deployment(anvil_url: str) -> Deployment:
    """The whole system, deployed once per test session. Tests run on snapshots of it."""
    from web3 import Web3

    roles = _accounts()
    return deploy_system(
        Web3(Web3.HTTPProvider(anvil_url)),
        roles["deployer"],
        admin=roles["deployer"].address,
        relayer=roles["relayer"].address,
        bank=roles["bank"].address,
    )


@pytest.fixture
def w3(anvil_url: str):
    """A connection to Anvil. Every change a test makes is undone after it."""
    from web3 import Web3

    web3 = Web3(Web3.HTTPProvider(anvil_url))
    snapshot = web3.provider.make_request("evm_snapshot", [])["result"]
    yield web3
    web3.provider.make_request("evm_revert", [snapshot])


@pytest.fixture
def chain(w3, deployment: Deployment) -> Chain:
    return Chain.of(Contracts(w3, deployment))
