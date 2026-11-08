"""The mock card provider and MockBank as one small HTTP service.

    uv run uvicorn veritas.mocks.app:create_mock_app --factory --port 8100

Veritas talks to it only over HTTP, the way it will talk to the real provider and bank.

No `from __future__ import annotations` here: the routes depend on an alias made inside
create_mock_app, and FastAPI can only resolve it from a real annotation, not a string.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker
from web3 import Web3

from veritas.chain import eip712
from veritas.chain.contracts import Contracts, Deployment
from veritas.chain.project import Credit
from veritas.db.session import make_engine, make_session_factory, session_scope
from veritas.mocks.bank import BankRefused, MockBank
from veritas.mocks.psp import DECLINED_CARDS, MockPSP, PSPError, payment_json, refund_json
from veritas.settings import Settings, get_settings


class PaymentIn(BaseModel):
    amount: int = Field(gt=0)
    card_number: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    save_card: bool = False
    customer_ref: str | None = None
    idempotency_key: str | None = None


class CardIn(BaseModel):
    customer_ref: str
    card_number: str


class ChargeIn(BaseModel):
    card_token: str
    amount: int = Field(gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str


class RefundIn(BaseModel):
    payment_id: str
    amount: int = Field(gt=0)
    idempotency_key: str


class CreditIn(BaseModel):
    project_id: UUID
    amounts: list[int]


class BatchIn(BaseModel):
    batch_id: int = Field(gt=0)
    root: str
    leaf_count: int = Field(gt=0)
    credits: list[CreditIn]
    payments: list[str]


class PayoutIn(BaseModel):
    instruction_id: int = Field(gt=0)
    amount: int = Field(gt=0)
    contractor_hash: str
    iban: str


class RefundPart(BaseModel):
    payment_id: str
    amount: int = Field(gt=0)


class BankRefundIn(BaseModel):
    instruction_id: int = Field(gt=0)
    amount: int = Field(gt=0)
    payments: list[RefundPart]


class AttestIn(BaseModel):
    day: int = Field(gt=0)
    cutoff_block: int = Field(ge=0)
    cutoff_time: int = Field(ge=0)


def _hex(value: str) -> bytes:
    return bytes.fromhex(value.removeprefix("0x"))


def create_mock_app(
    settings: Settings | None = None,
    chain: Contracts | None = None,
    sessions: sessionmaker[Session] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    if sessions is None:
        sessions = make_session_factory(make_engine(settings.database_url))
    if chain is None and settings.chain_rpc_url and settings.deployment_file:
        w3 = Web3(Web3.HTTPProvider(settings.chain_rpc_url))
        chain = Contracts(w3, Deployment.load(settings.deployment_file))
    domain = eip712.Domain(chain.deployment.chain_id, chain.deployment.hub) if chain else None

    app = FastAPI(title="Veritas mocks", summary="A card provider and a partner bank for the demo")

    def session() -> Iterator[Session]:
        yield from session_scope(sessions)

    def services(db: Annotated[Session, Depends(session)]) -> tuple[MockPSP, MockBank]:
        if domain is None:
            raise HTTPException(503, "the bank needs the chain settings")
        psp = MockPSP(db)

        def refund_card(payment_id: str, amount: int, key: str) -> bool:
            refund = psp.refund(payment_id=payment_id, amount=amount, idempotency_key=key)
            return refund.status == "succeeded"

        if settings.mockbank_key is None:
            raise HTTPException(503, "set VERITAS_MOCKBANK_KEY, the key the hub knows as the bank")
        bank = MockBank(
            db,
            key=bytes.fromhex(settings.mockbank_key.get_secret_value().removeprefix("0x")),
            domain=domain,
            chain=chain,
            refund_card=refund_card,
            closed_accounts=settings.mockbank_closed_accounts,
        )
        # In bank mode the bank is the acquirer: card money lands in its escrow account.
        psp.on_payment = bank.receive_card_payment
        psp.on_refund = bank.card_refunded
        return psp, bank

    def psp_key(authorization: Annotated[str | None, Header()] = None) -> None:
        if authorization != f"Bearer {settings.psp_api_key.get_secret_value()}":
            raise HTTPException(401, "wrong API key")

    def bank_key(authorization: Annotated[str | None, Header()] = None) -> None:
        if authorization != f"Bearer {settings.bank_api_key.get_secret_value()}":
            raise HTTPException(401, "wrong API key")

    Services = Annotated[tuple[MockPSP, MockBank], Depends(services)]

    @app.post("/psp/payments", dependencies=[Depends(psp_key)])
    def create_payment(body: PaymentIn, both: Services) -> dict[str, Any]:
        try:
            return payment_json(both[0].pay(**body.model_dump()))
        except PSPError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/psp/cards", dependencies=[Depends(psp_key)])
    def save_card(body: CardIn, both: Services) -> dict[str, Any]:
        if body.card_number in DECLINED_CARDS:
            raise HTTPException(400, "the card was declined")
        try:
            card = both[0].save_card(body.customer_ref, body.card_number)
        except PSPError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"token": card.token, "last4": card.last4}

    @app.post("/psp/charges", dependencies=[Depends(psp_key)])
    def create_charge(body: ChargeIn, both: Services) -> dict[str, Any]:
        try:
            return payment_json(both[0].charge(**body.model_dump()))
        except PSPError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/psp/refunds", dependencies=[Depends(psp_key)])
    def create_refund(body: RefundIn, both: Services) -> dict[str, Any]:
        try:
            return refund_json(both[0].refund(**body.model_dump()))
        except PSPError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/psp/payments/{payment_id}", dependencies=[Depends(psp_key)])
    def get_payment(payment_id: str, both: Services) -> dict[str, Any]:
        payment = both[0].get(payment_id)
        if payment is None:
            raise HTTPException(404, "no such payment")
        return payment_json(payment)

    @app.post("/psp/cards/{token}/expire", dependencies=[Depends(psp_key)])
    def expire_card(token: str, both: Services) -> dict[str, str]:
        both[0].expire_card(token)
        return {"token": token, "status": "expired"}

    @app.post("/psp/webhooks/deliver", dependencies=[Depends(psp_key)])
    def deliver_webhooks(both: Services) -> dict[str, int]:
        """Sends pending webhooks to Veritas, in order, stopping at the first that fails."""
        delivered = 0
        secret = settings.psp_webhook_secret.get_secret_value()
        for webhook in both[0].pending_webhooks():
            body, header = both[0].signed(webhook, secret)
            webhook.attempts += 1
            response = httpx.post(
                settings.psp_webhook_url,
                content=body,
                headers={"Content-Type": "application/json", "Veritas-PSP-Signature": header},
                timeout=10,
            )
            if response.status_code >= 300:
                break
            webhook.delivered_at = datetime.now(UTC)
            delivered += 1
        return {"delivered": delivered}

    @app.post("/bank/batches", dependencies=[Depends(bank_key)])
    def attest_batch(body: BatchIn, both: Services) -> dict[str, str]:
        credits = [Credit(c.project_id, tuple(c.amounts)) for c in body.credits]
        try:
            signature = both[1].attest_batch(
                batch_id=body.batch_id,
                root=_hex(body.root),
                leaf_count=body.leaf_count,
                credits=credits,
                payments=body.payments,
            )
        except BankRefused as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"signature": "0x" + signature.hex()}

    @app.post("/bank/payouts", dependencies=[Depends(bank_key)])
    def payout(body: PayoutIn, both: Services) -> dict[str, str]:
        try:
            result = both[1].execute_payout(
                instruction_id=body.instruction_id,
                amount=body.amount,
                contractor_hash=_hex(body.contractor_hash),
                iban=body.iban,
            )
        except BankRefused as exc:
            raise HTTPException(409, str(exc)) from exc
        return {
            "status": result.status,
            "payment_ref": "0x" + result.payment_ref.hex(),
            "signature": "0x" + result.signature.hex(),
        }

    @app.post("/bank/refunds", dependencies=[Depends(bank_key)])
    def refund(body: BankRefundIn, both: Services) -> dict[str, str]:
        try:
            result = both[1].execute_refund(
                instruction_id=body.instruction_id,
                amount=body.amount,
                payments=[(part.payment_id, part.amount) for part in body.payments],
            )
        except BankRefused as exc:
            raise HTTPException(409, str(exc)) from exc
        return {
            "status": result.status,
            "payment_ref": "0x" + result.payment_ref.hex(),
            "signature": "0x" + result.signature.hex(),
        }

    @app.post("/bank/attestations", dependencies=[Depends(bank_key)])
    def attest_balance(body: AttestIn, both: Services) -> dict[str, Any]:
        hub = chain.deployment.hub if chain else None
        attestation = both[1].attest_balance(**body.model_dump(), hub=hub)
        return {
            "day": attestation.day,
            "balance": attestation.balance_qapik,
            "statement": attestation.statement.decode(),
            "signature": "0x" + attestation.signature.hex(),
        }

    @app.get("/bank/statement", dependencies=[Depends(bank_key)])
    def statement(both: Services) -> dict[str, int]:
        return {"escrow": both[1].escrow_balance(), "pending": both[1].pending_balance()}

    return app
