"""HTTP clients for the card provider and the partner bank.

Veritas only ever reaches them through these, so the mocks in development and the real
services later sit behind the same calls. Each takes an httpx.Client with its base URL set,
which lets tests point them at the mock app in-process.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from veritas.chain.project import Credit


class ProviderError(RuntimeError):
    """The provider or the bank refused a request, or could not be reached."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _call(client: httpx.Client, method: str, path: str, api_key: str, **kwargs: Any) -> Any:
    try:
        response = client.request(
            method, path, headers={"Authorization": f"Bearer {api_key}"}, **kwargs
        )
    except httpx.HTTPError as exc:
        raise ProviderError(f"{method} {path} failed: {exc}") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise ProviderError(f"{method} {path}: {detail}", response.status_code)
    return response.json()


class PspClient:
    def __init__(self, client: httpx.Client, api_key: str) -> None:
        self.client = client
        self.api_key = api_key

    def create_payment(
        self,
        *,
        amount: int,
        card_number: str,
        metadata: dict[str, Any],
        idempotency_key: str,
        save_card: bool = False,
        customer_ref: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "amount": amount,
            "card_number": card_number,
            "metadata": metadata,
            "save_card": save_card,
            "customer_ref": customer_ref,
            "idempotency_key": idempotency_key,
        }
        return _call(self.client, "POST", "/psp/payments", self.api_key, json=body)

    def get_payment(self, payment_id: str) -> dict[str, Any]:
        return _call(self.client, "GET", f"/psp/payments/{payment_id}", self.api_key)

    def save_card(self, *, customer_ref: str, card_number: str) -> dict[str, Any]:
        """Saves a card for merchant-initiated charges. Veritas keeps only the token."""
        body = {"customer_ref": customer_ref, "card_number": card_number}
        return _call(self.client, "POST", "/psp/cards", self.api_key, json=body)

    def charge(
        self, *, card_token: str, amount: int, metadata: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        body = {
            "card_token": card_token,
            "amount": amount,
            "metadata": metadata,
            "idempotency_key": idempotency_key,
        }
        return _call(self.client, "POST", "/psp/charges", self.api_key, json=body)

    def refund(self, *, payment_id: str, amount: int, idempotency_key: str) -> dict[str, Any]:
        body = {"payment_id": payment_id, "amount": amount, "idempotency_key": idempotency_key}
        return _call(self.client, "POST", "/psp/refunds", self.api_key, json=body)


class BankClient:
    def __init__(self, client: httpx.Client, api_key: str) -> None:
        self.client = client
        self.api_key = api_key

    def attest_batch(
        self,
        *,
        batch_id: int,
        root: bytes,
        leaf_count: int,
        credits: Sequence[Credit],
        payments: Sequence[str],
    ) -> bytes:
        body = {
            "batch_id": batch_id,
            "root": "0x" + root.hex(),
            "leaf_count": leaf_count,
            "credits": [
                {"project_id": str(c.project_id), "amounts": list(c.amounts)} for c in credits
            ],
            "payments": list(payments),
        }
        result = _call(self.client, "POST", "/bank/batches", self.api_key, json=body)
        return bytes.fromhex(result["signature"][2:])

    def payout(
        self, *, instruction_id: int, amount: int, contractor_hash: bytes, iban: str
    ) -> dict[str, Any]:
        body = {
            "instruction_id": instruction_id,
            "amount": amount,
            "contractor_hash": "0x" + contractor_hash.hex(),
            "iban": iban,
        }
        return _call(self.client, "POST", "/bank/payouts", self.api_key, json=body)

    def refund(
        self, *, instruction_id: int, amount: int, payments: Sequence[tuple[str, int]]
    ) -> dict[str, Any]:
        body = {
            "instruction_id": instruction_id,
            "amount": amount,
            "payments": [{"payment_id": p, "amount": a} for p, a in payments],
        }
        return _call(self.client, "POST", "/bank/refunds", self.api_key, json=body)

    def attest_balance(self, *, day: int, cutoff_block: int, cutoff_time: int) -> dict[str, Any]:
        body = {"day": day, "cutoff_block": cutoff_block, "cutoff_time": cutoff_time}
        return _call(self.client, "POST", "/bank/attestations", self.api_key, json=body)

    def statement(self) -> dict[str, int]:
        return _call(self.client, "GET", "/bank/statement", self.api_key)
