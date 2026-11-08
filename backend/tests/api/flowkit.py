"""Helpers for the end-to-end flows: the API, PostgreSQL and a real chain on Anvil."""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_defunct
from sqlalchemy import select
from support import ok

from chainkit import settle
from veritas.chain.handlers import build_handlers
from veritas.chain.indexer import Indexer, IndexerConfig
from veritas.chain.relayer import Relayer, RelayerConfig
from veritas.db.models import Charity, User
from veritas.mocks.models import MockWebhook
from veritas.payments import webhooks
from veritas.services.passports import create_project

EXAMPLE = Path(__file__).resolve().parents[3] / "docs" / "examples" / "passport.example.json"
EXAMPLE_ID = "6f1c2a9e-3b7d-4e2a-9c41-8d5b2f0e7a13"


def example_doc() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def workers(sessions, chain, accounts):
    """A relayer and an indexer as the worker process runs them, tuned for Anvil."""
    relayer = Relayer(
        sessions,
        chain.contracts,
        {"relayer": accounts["relayer"], "admin": accounts["deployer"]},
        RelayerConfig(min_priority_fee=10**9, bump_after_seconds=3600),
    )
    indexer = Indexer(sessions, chain.contracts, build_handlers(), IndexerConfig(chunk=500))
    return relayer, indexer


def run(relayer, indexer, w3) -> None:
    settle(relayer, indexer, w3)


def set_charity_key(client, charity_id: str, charity_admin, key) -> dict:
    base = f"/v1/charities/{charity_id}"
    issued = ok(client.post(f"{base}/signer/challenge", headers=charity_admin.headers), 201)
    signature = Account.from_key(key.key).sign_message(encode_defunct(text=issued["message"]))
    body = {
        "address": key.address,
        "nonce": issued["nonce"],
        "signature": signature.signature.to_0x_hex(),
    }
    return ok(client.put(f"{base}/signer", json=body, headers=charity_admin.headers))


def launch_doc(client, db, charity_admin, charity_id: str, charity_key, doc: dict) -> str:
    """Drafts a Passport, signs its launch message with the charity key and publishes it."""
    user = db.get(User, charity_admin.user_id)
    charity = db.get(Charity, uuid.UUID(charity_id))
    create_project(db, charity, user, project_id=uuid.UUID(doc["project_id"]))
    db.commit()
    base = f"/v1/projects/{doc['project_id']}"
    ok(client.put(f"{base}/passport", json=doc, headers=charity_admin.headers))
    typed = ok(client.get(f"{base}/launch-message", headers=charity_admin.headers))
    signed = Account.sign_typed_data(charity_key.key, full_message=typed)
    body = {"charity_signature": signed.signature.to_0x_hex()}
    ok(client.post(f"{base}/publish", json=body, headers=charity_admin.headers))
    return doc["project_id"]


def launch_example(client, db, charity_admin, charity_id: str, charity_key) -> str:
    return launch_doc(client, db, charity_admin, charity_id, charity_key, example_doc())


def another_project_doc(title: str = "Clean water for Yeni Qala") -> dict:
    """A second project in the same category, for redirects."""
    doc = example_doc()
    doc["project_id"] = str(uuid.uuid4())
    doc["title"] = title
    return doc


def live_example(client, db, chain, w3, accounts, sessions, charity_admin, verified_charity):
    """The example project, launched on Anvil and live in the database."""
    set_charity_key(client, verified_charity["id"], charity_admin, accounts["charity"])
    project_id = launch_example(
        client, db, charity_admin, verified_charity["id"], accounts["charity"]
    )
    relayer, indexer = workers(sessions, chain, accounts)
    run(relayer, indexer, w3)
    return project_id, relayer, indexer


def deliver_webhooks(client, db, settings) -> list:
    """Delivers the mock provider's pending webhooks to the API, as it would over HTTP."""
    secret = settings.psp_webhook_secret.get_secret_value().encode()
    responses = []
    pending = db.scalars(
        select(MockWebhook).where(MockWebhook.delivered_at.is_(None)).order_by(MockWebhook.id)
    ).all()
    for webhook in pending:
        header = webhooks.sign(secret, webhook.body, int(time.time()))
        response = client.post(
            "/v1/webhooks/psp",
            content=webhook.body,
            headers={"Content-Type": "application/json", webhooks.SIGNATURE_HEADER: header},
        )
        responses.append(response)
        webhook.delivered_at = datetime.now(UTC)
    db.commit()
    return responses


def donate(client, donor, project_id, holder, amount, card="4242424242424242") -> dict:
    body = {"amount_qapik": amount, "holder": holder, "card_number": card}
    url = f"/v1/projects/{project_id}/donations"
    return ok(client.post(url, json=body, headers=donor.headers), 201)


def leaf_values(leaf: dict) -> tuple:
    """A donor receipt's leaf, as the contracts take it."""
    return (
        bytes.fromhex(leaf["donationId"][2:]),
        leaf["holder"],
        bytes.fromhex(leaf["projectId"][2:]),
        leaf["milestone"],
        leaf["amount"],
        bytes.fromhex(leaf["trigger"][2:]),
        bytes.fromhex(leaf["salt"][2:]),
    )
