"""Helpers for the Phase 8 flows: real evidence on-chain, officer and donor signatures, time."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import timedelta

from eth_account import Account
from flowkit import deliver_webhooks, donate
from sqlalchemy import select
from support import OFFICER, ok

from chainkit import mine
from evidence.kit import (
    FAR_AWAY,
    IN_WINDOW,
    Clock,
    FixedBoxes,
    attest,
    manifest_for,
    proof_set,
    register_device,
    sign_manifest,
    start,
    submit,
    upload,
)
from veritas.db.models import Milestone
from veritas.db.models.evidence import CheckReport, EvidenceBundle
from veritas.evidence.ipfs import FakeIpfs
from veritas.evidence.pipeline import EvidencePipeline
from veritas.payments.batches import build_batch

OFFICER_PHONE = "+994 50 444 44 44"


def reviewing_officer(client, admin, login):
    """The example Passport's officer, linked to a phone so they can review in the app."""
    ok(
        client.post(
            "/v1/officers", json={**OFFICER, "phone": OFFICER_PHONE}, headers=admin.headers
        ),
        201,
    )
    return login(OFFICER_PHONE)


def fund(client, db, mocks, donors) -> None:
    """Card donations from (person, holder key, amount) and the batch that anchors them."""
    for person, key, amount, project_id in donors:
        donate(client, person, project_id, key.address, amount)
    deliver_webhooks(client, db, mocks["settings"])
    build_batch(db, mocks["bank"])
    db.commit()


def milestone_row(db, project_id, index) -> Milestone:
    db.expire_all()
    return db.scalars(
        select(Milestone).where(
            Milestone.project_id == uuid.UUID(project_id), Milestone.index == index
        )
    ).one()


class FieldEvidence:
    """The charity's side of Phase 6, for the decision flows: a capture on site through the
    API, the evidence worker's checks and public copy, and the admin's signature. Nothing is
    put on-chain that the database cannot account for.

    The API's evidence clock is set to 10 March 2027, inside milestone 0's window; the chain
    keeps its own time, well before the escrow's evidence deadline."""

    def __init__(self, client, app, settings, sessions, charity_admin, charity_key) -> None:
        self.client = client
        self.settings = settings
        self.person = charity_admin
        self.charity_key = charity_key
        self.clock = Clock(IN_WINDOW)
        self.phone = Account.create()
        register_device(client, charity_admin, self.phone)
        self.pipeline = EvidencePipeline(
            sessions,
            storage=app.state.storage,
            settings=settings,
            ipfs=FakeIpfs(),
            detector=FixedBoxes(),
        )
        self.rounds = 0

    def anchor(self, db, project_id, index: int = 0, passed: bool = True) -> tuple[bytes, bytes]:
        """Queues one checked, signed bundle for the relayer. Returns its bundle and report
        hashes. With `passed=False`, one site photo is taken in Baku, 150 km off the site."""
        self.rounds += 1
        captures = proof_set(self.clock.now, seed=self.rounds)
        if not passed:
            captures[0] = dataclasses.replace(captures[0], at=FAR_AWAY)
        session = ok(start(self.client, self.person, project_id, self.phone, index), 201)
        self.clock.now = max(c.captured_at for c in captures) + timedelta(minutes=1)
        for capture in captures:
            ok(upload(self.client, self.person, session["id"], capture), 201)
        data = manifest_for(session, self.phone.address, captures)
        token = attest(self.settings, self.phone.address, session["id"], data)
        signature = sign_manifest(self.phone, data)
        bundle = ok(submit(self.client, self.person, session["id"], data, signature, token), 201)
        assert self.pipeline.run_once() == 2  # checked, then published

        base = f"/v1/evidence/{bundle['id']}"
        typed = ok(self.client.get(f"{base}/evidence-message", headers=self.person.headers))
        signed = Account.sign_typed_data(self.charity_key.key, full_message=typed).signature
        # The admin has looked at the redacted photos: none shows a face or a plate.
        body = {"charity_signature": signed.to_0x_hex(), "publish_photos": [1, 2, 3, 4]}
        ok(self.client.post(f"{base}/anchor", json=body, headers=self.person.headers))
        assert self.pipeline.run_once() == 1  # the signed public copy goes to IPFS

        db.expire_all()
        row = db.get_one(EvidenceBundle, uuid.UUID(bundle["id"]))
        report = db.scalars(select(CheckReport).where(CheckReport.bundle_id == row.id)).one()
        assert report.passed is passed, "the captures did not give the result the test wanted"
        self.clock.advance(hours=1)
        return row.bundle_hash, report.sha256


def sign_typed(client, path, params, person, key) -> str:
    typed = ok(client.get(path, params=params, headers=person.headers))
    return Account.sign_typed_data(key.key, full_message=typed).signature.to_0x_hex()


def warp(w3, seconds: int) -> None:
    w3.provider.make_request("evm_increaseTime", [seconds])
    mine(w3, 1)
