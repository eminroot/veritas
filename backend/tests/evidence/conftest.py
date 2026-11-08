"""A live example project without a chain, a field worker with a phone key, and the clock.

The project is published through the services and then marked live by hand, the way the
indexer would after the escrow is created, so these tests need PostgreSQL but not Anvil.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from eth_account import Account

from veritas.api.routes.evidence import evidence_clock
from veritas.db.models import (
    Charity,
    CharityMember,
    CharityStatus,
    Contractor,
    ContractorStatus,
    MemberRole,
    Officer,
    Project,
    ProjectStatus,
    User,
)
from veritas.evidence.attestation import attestation_verifier
from veritas.evidence.checks import Tools
from veritas.evidence.ipfs import FakeIpfs
from veritas.evidence.pipeline import EvidencePipeline
from veritas.services.passports import create_project, publish_passport, save_draft

from .kit import IN_WINDOW, Clock, FixedBoxes, capture_bundle, register_device

EXAMPLE = Path(__file__).resolve().parents[3] / "docs" / "examples" / "passport.example.json"
EXAMPLE_ID = uuid.UUID("6f1c2a9e-3b7d-4e2a-9c41-8d5b2f0e7a13")
ESCROW = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
OFFICER_ADDRESS = "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65"


def example_doc() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def clock(app):
    """The evidence rules' clock, set inside milestone 0's window until the test moves it."""
    clock = Clock(IN_WINDOW)
    app.dependency_overrides[evidence_clock] = clock
    yield clock
    app.dependency_overrides.pop(evidence_clock, None)


@pytest.fixture
def charity_admin(login):
    return login("+994 50 111 11 11")


@pytest.fixture
def field_worker(login):
    return login("+994 50 333 33 33")


@pytest.fixture
def stranger(login):
    return login("+994 50 444 44 44")


@pytest.fixture
def project(db, charity_admin, field_worker) -> Project:
    """The example project, published and live, with the admin and a field worker."""
    admin = db.get_one(User, charity_admin.user_id)
    now = datetime(2026, 11, 1, tzinfo=UTC)
    charity = Charity(
        legal_name="Bərəkət İctimai Birliyi",
        voen="1700000011",
        legal_form="Public union",
        legal_address="Bakı, Nizami küçəsi 10",
        director_name="Leyla Məmmədova",
        contact_email="info@bereket.example.az",
        contact_phone="+994123456789",
        status=CharityStatus.VERIFIED,
        verified_at=now,
        signer_address=Account.from_key(b"\x07" * 32).address,
        created_by=admin.id,
    )
    db.add(charity)
    db.flush()
    db.add(CharityMember(charity_id=charity.id, user_id=admin.id, role=MemberRole.ADMIN))
    db.add(
        CharityMember(
            charity_id=charity.id, user_id=field_worker.user_id, role=MemberRole.FIELD_WORKER
        )
    )
    db.add(
        Contractor(
            legal_name="Dağ Tikinti MMC",
            voen="1300000021",
            iban="AZ21NABZ00000000137010001944",
            legal_address="Qəbələ rayonu, Yeni Qala kəndi",
            director_name="Rauf Həsənov",
            status=ContractorStatus.VERIFIED,
            charity_id=charity.id,
            created_by=admin.id,
        )
    )
    db.add(
        Officer(
            name="Nərmin Əliyeva",
            organisation="Sample Audit Partners",
            address=OFFICER_ADDRESS,
            created_by=admin.id,
        )
    )
    db.flush()
    project, _ = create_project(db, charity, admin, project_id=EXAMPLE_ID)
    save_draft(db, project, admin, example_doc())
    publish_passport(db, project, admin)
    project.status = ProjectStatus.LIVE
    project.escrow_address = ESCROW
    project.charity_signer = charity.signer_address  # as the launch records it
    db.commit()
    return project


@pytest.fixture
def phone(client, field_worker):
    """The field worker's registered phone key."""
    account = Account.create()
    register_device(client, field_worker, account)
    return account


@pytest.fixture
def make(client, settings, clock, project, field_worker, phone):
    """Capture a bundle of the given files through the API, as the field worker's phone."""

    def make_bundle(captures, **options):
        return capture_bundle(
            client, settings, clock, field_worker, project.id, phone, captures, **options
        )

    return make_bundle


@pytest.fixture
def pipeline(sessions, app, settings):
    """The evidence worker with an in-memory IPFS and a detector that finds nothing."""
    return EvidencePipeline(
        sessions,
        storage=app.state.storage,
        settings=settings,
        ipfs=FakeIpfs(),
        detector=FixedBoxes(),
    )


@pytest.fixture
def sessions(engine):
    from veritas.db.session import make_session_factory

    return make_session_factory(engine)


@pytest.fixture
def tools(app, settings) -> Tools:
    return Tools(
        storage=app.state.storage, attestation=attestation_verifier(settings), settings=settings
    )
