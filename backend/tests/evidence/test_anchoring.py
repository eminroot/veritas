"""Anchoring: the charity's EIP-712 signature, then two outbox rows in order.

The chain itself is not needed to test what gets queued: anchoring only uses the chain's
EIP-712 domain and asks whether the signer has code (a Safe), so a stand-in with a domain and
no code anywhere is enough here. tests/api/test_flow_evidence.py sends the same rows to a
real escrow on Anvil.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from eth_account import Account
from sqlalchemy import func, select, update

from veritas.chain import eip712
from veritas.chain.codec import decode_args
from veritas.db.models import Charity, Milestone, Project
from veritas.db.models.chain import Alert, ChainOutbox
from veritas.db.models.evidence import CheckReport, EvidenceBundle
from veritas.evidence.anchoring import MAX_CHECKS_TRIES, resend_checks

from .conftest import ESCROW, EXAMPLE_ID
from .kit import proof_set, start
from .test_capture import error

CHARITY = Account.from_key(b"\x07" * 32)
"""The charity's signing key in the test project (see conftest)."""


@pytest.fixture
def chain(app):
    no_code = SimpleNamespace(eth=SimpleNamespace(get_code=lambda address: b""))
    stand_in = SimpleNamespace(domain=eip712.Domain(31337, "0x" + "11" * 20), w3=no_code)
    app.state.chain = stand_in
    yield stand_in
    app.state.chain = None


@pytest.fixture
def published(clock, make, pipeline):
    bundle = make(proof_set(clock.now))
    pipeline.run_once()
    return bundle


def message(client, person, bundle):
    return client.get(f"/v1/evidence/{bundle['id']}/evidence-message", headers=person.headers)


def anchor(client, person, bundle, signature, photos=()):
    return client.post(
        f"/v1/evidence/{bundle['id']}/anchor",
        json={"charity_signature": signature, "publish_photos": list(photos)},
        headers=person.headers,
    )


def charity_signs(typed: dict) -> str:
    return Account.sign_typed_data(CHARITY.key, full_message=typed).signature.to_0x_hex()


def test_without_a_chain_nothing_is_anchored(client, published, charity_admin):
    error(message(client, charity_admin, published), 409, "no_chain")
    error(anchor(client, charity_admin, published, "0x" + "11" * 65), 409, "no_chain")


def test_the_charity_signs_and_the_evidence_then_the_checks_are_queued(
    client, db, chain, published, charity_admin
):
    typed = message(client, charity_admin, published).json()
    assert typed["primaryType"] == "Evidence"
    assert typed["message"] == {
        "projectId": "0x" + EXAMPLE_ID.hex,
        "milestone": 0,
        "attempt": 1,
        "bundleHash": published["bundle_hash"],
    }

    response = anchor(client, charity_admin, published, charity_signs(typed))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["anchoring"]["submit_evidence"] == "pending"
    assert body["anchoring"]["record_checks"] == "pending"
    assert body["status"] == "published"  # anchored once the indexer sees it on-chain

    row = db.get_one(EvidenceBundle, uuid.UUID(published["id"]))
    report = db.scalars(select(CheckReport)).one()
    submit, checks = db.scalars(select(ChainOutbox).order_by(ChainOutbox.id)).all()
    assert (submit.kind, submit.function, checks.kind, checks.function) == (
        "submit_evidence",
        "submitEvidence",
        "record_checks",
        "recordChecks",
    )
    assert submit.address == checks.address == ESCROW
    assert submit.project_id == checks.project_id == EXAMPLE_ID
    assert submit.dedupe_key == f"submit_evidence:{published['id']}"
    assert checks.dedupe_key == f"record_checks:{published['id']}"
    assert decode_args("MilestoneEscrow", "submitEvidence", submit.args) == [
        0,
        row.bundle_hash,
        row.public_cid,
        row.charity_signature,
    ]
    assert decode_args("MilestoneEscrow", "recordChecks", checks.args) == [
        0,
        1,
        report.sha256,
        True,
    ]
    assert (row.submit_outbox_id, row.checks_outbox_id) == (submit.id, checks.id)

    error(anchor(client, charity_admin, published, charity_signs(typed)), 409, "not_anchorable")


def test_a_signature_from_another_key_is_refused(client, db, chain, published, charity_admin):
    typed = message(client, charity_admin, published).json()
    forged = Account.sign_typed_data(Account.create().key, full_message=typed)
    error(
        anchor(client, charity_admin, published, forged.signature.to_0x_hex()), 403, "bad_signature"
    )
    assert db.scalars(select(ChainOutbox)).all() == []


def test_only_charity_admins_sign_off_evidence(client, chain, published, field_worker):
    error(message(client, field_worker, published), 403, "role_required")


def test_a_bundle_is_signed_only_once_its_public_copy_is_out(
    client, clock, chain, make, charity_admin
):
    draft = make(proof_set(clock.now))
    body = error(message(client, charity_admin, draft), 409, "not_anchorable")
    assert "draft" in body["message"]


def test_a_bundle_for_an_attempt_that_moved_on_is_refused(
    client, db, chain, published, charity_admin
):
    db.execute(
        update(Milestone)
        .where(Milestone.project_id == EXAMPLE_ID, Milestone.index == 0)
        .values(status="rejected", attempt=1)
    )
    db.commit()
    body = error(message(client, charity_admin, published), 409, "attempt_moved")
    assert "attempt 1" in body["message"] and "attempt 2" in body["message"]


def test_after_the_deadline_nothing_is_anchored(client, clock, chain, published, charity_admin):
    clock.advance(days=40)
    error(message(client, charity_admin, published), 409, "deadline_passed")


def test_one_signed_bundle_per_attempt(
    client, clock, chain, make, pipeline, published, charity_admin, field_worker, phone, project
):
    clock.advance(minutes=90)
    second = make(proof_set(clock.now, seed=2))
    pipeline.run_once()
    typed = message(client, charity_admin, published).json()
    assert anchor(client, charity_admin, published, charity_signs(typed)).status_code == 200

    error(message(client, charity_admin, second), 409, "evidence_in_flight")
    clock.advance(minutes=1)
    error(start(client, field_worker, project.id, phone), 409, "evidence_in_flight")


def test_evidence_the_chain_refused_is_void_and_the_attempt_takes_new_evidence(
    client, db, clock, chain, make, pipeline, published, charity_admin, field_worker, phone, project
):
    typed = message(client, charity_admin, published).json()
    assert anchor(client, charity_admin, published, charity_signs(typed)).status_code == 200
    # The relayer finds that submitEvidence would revert, so both calls fail.
    db.execute(
        update(ChainOutbox).values(status="failed", last_error="would revert: BadSignature(0x90F7)")
    )
    db.commit()

    clock.advance(minutes=90)
    second = make(proof_set(clock.now, seed=2))  # a new session opens: the attempt is free
    pipeline.run_once()
    voided = client.get(f"/v1/evidence/{published['id']}", headers=charity_admin.headers).json()
    assert voided["status"] == "void"
    assert "BadSignature" in voided["void_reason"]
    assert db.scalars(select(Alert.kind)).all().count("evidence_void") == 1

    typed = message(client, charity_admin, second).json()
    body = anchor(client, charity_admin, second, charity_signs(typed)).json()
    assert body["anchoring"]["submit_evidence"] == "pending"
    keys = db.scalars(select(ChainOutbox.dedupe_key).where(ChainOutbox.status == "pending")).all()
    assert sorted(keys) == [f"record_checks:{second['id']}", f"submit_evidence:{second['id']}"]


def test_the_escrow_keeps_the_charity_key_it_was_launched_with(
    client, db, chain, published, charity_admin
):
    project = db.get_one(Project, EXAMPLE_ID)
    charity = db.get_one(Charity, project.charity_id)
    charity.signer_address = Account.create().address  # a new phone, for later projects
    db.commit()
    typed = message(client, charity_admin, published).json()
    refused = error(
        anchor(client, charity_admin, published, "0x" + "11" * 65), 403, "bad_signature"
    )
    assert CHARITY.address in refused["message"]
    response = anchor(client, charity_admin, published, charity_signs(typed))
    assert response.status_code == 200, response.text


def test_a_stopped_project_takes_no_evidence(client, db, chain, published, charity_admin):
    db.execute(update(Project).where(Project.id == EXAMPLE_ID).values(status="stopped"))
    db.commit()
    error(message(client, charity_admin, published), 409, "project_not_live")


def test_checks_the_chain_refused_after_the_evidence_landed_are_sent_again(
    client, db, chain, published, charity_admin
):
    typed = message(client, charity_admin, published).json()
    assert anchor(client, charity_admin, published, charity_signs(typed)).status_code == 200
    submit, checks = db.scalars(select(ChainOutbox).order_by(ChainOutbox.id)).all()
    submit.status, checks.status = "confirmed", "failed"
    db.execute(
        update(Milestone)
        .where(Milestone.project_id == EXAMPLE_ID, Milestone.index == 0)
        .values(status="evidence_submitted", attempt=1)
    )
    db.commit()

    assert resend_checks(db) == 0  # it waits a little first: the cause may be passing
    long_ago = func.now() - timedelta(days=7)
    db.execute(update(ChainOutbox).values(updated_at=long_ago))
    db.commit()
    assert resend_checks(db) == 1
    db.commit()
    again = db.scalars(select(ChainOutbox).where(ChainOutbox.status == "pending")).one()
    assert again.function == "recordChecks" and again.dedupe_key == f"{checks.dedupe_key}:2"
    assert db.get_one(EvidenceBundle, uuid.UUID(published["id"])).checks_outbox_id == again.id
    assert resend_checks(db) == 0  # on its way

    for _ in range(MAX_CHECKS_TRIES):
        db.execute(
            update(ChainOutbox)
            .where(ChainOutbox.status == "pending")
            .values(status="failed", last_error="would revert: 0xc64891a5")
        )
        db.execute(update(ChainOutbox).values(updated_at=long_ago))
        db.commit()
        resend_checks(db)
        db.commit()
    tries = db.scalars(select(ChainOutbox).where(ChainOutbox.function == "recordChecks")).all()
    assert len(tries) == MAX_CHECKS_TRIES
    stuck = db.scalars(select(Alert).where(Alert.kind == "evidence_checks_stuck")).one()
    assert "NotRelayer" in stuck.message


def test_a_cancelled_checks_row_is_a_persons_decision(client, db, chain, published, charity_admin):
    typed = message(client, charity_admin, published).json()
    assert anchor(client, charity_admin, published, charity_signs(typed)).status_code == 200
    submit, checks = db.scalars(select(ChainOutbox).order_by(ChainOutbox.id)).all()
    submit.status, checks.status = "confirmed", "cancelled"
    db.execute(
        update(Milestone)
        .where(Milestone.project_id == EXAMPLE_ID, Milestone.index == 0)
        .values(status="evidence_submitted", attempt=1)
    )
    db.execute(update(ChainOutbox).values(updated_at=func.now() - timedelta(days=7)))
    db.commit()
    assert resend_checks(db) == 0
    assert db.scalars(select(Alert)).all() == []
