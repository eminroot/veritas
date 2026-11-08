"""The indexer handlers for money in: batches, settlement and receipts."""

from __future__ import annotations

from veritas.chain.indexer import Handlers
from veritas.payments import batches


def register(handlers: Handlers) -> None:
    handlers.on("DonationLedger", "BatchAnchored")(batches.on_batch_anchored)
    handlers.on("DonationLedger", "BatchSettled")(batches.on_batch_settled)
    handlers.on("ReceiptToken", "ReceiptMinted")(batches.on_receipt_minted)
    handlers.on("ReceiptToken", "KeyRotated")(batches.on_key_rotated)
    handlers.expect("anchor_batch", "DonationLedger", "BatchAnchored")
    handlers.expect("attest_balance", "DonationLedger", "BalanceAttested")
