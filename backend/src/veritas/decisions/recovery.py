"""Moving a donor's receipt to a new key, with or without the old phone.

The receipt is the donor's identity in a project: votes and refund choices are checked
against the key that controls it. A donor who still has that key signs a KeyRotation message
and the receipt moves at once. A donor who lost their phone proves who they are again, with
the account (and so the phone number) the receipt belongs to and a card that account paid
with, and Veritas asks the receipt contract to move the receipt. That request waits 48 hours
on-chain, during which the old key can still cancel it with a RotationCancel signature, so
someone who took over the phone number alone cannot take the receipt. A job finishes the
rotations whose wait is over.

A receipt belongs to the account its donor key belongs to (payments/holders.py): no other
account can donate under that key, in any project, so no other account can claim the
receipt. The card check compares the last four digits with the cards the account paid with
before the receipt was issued, a moment no later login can move, so a card added after
taking over the account does not count. The answer is one secret for the whole account, so
wrong answers count for the account, on its locked row, so that answers sent at the same
moment count too: five lock the recovery of all its receipts until support unlocks it, and
the four digits cannot be guessed. With a real
card provider the check becomes a zero-amount verification of the card.

Signatures are checked against the key the chain holds now (controllerOf at the latest
block), not the database's copy, which follows finalised events and lags a rotation. A signed
move or refusal the chain refused can be sent again, a few times; after that the API says the
chain refused it, rather than that it was queued.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from eth_utils import is_address, to_checksum_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.chain import eip712
from veritas.chain.contracts import Contracts
from veritas.chain.outbox import enqueue, enqueue_again, require_sent
from veritas.db.models import Project, User
from veritas.db.models.chain import ChainEvent, ChainOutbox, OutboxStatus
from veritas.db.models.money import Donation, Receipt, ReceiptStatus
from veritas.payments.holders import holder_owner
from veritas.services.errors import (
    BadRequest,
    Conflict,
    Forbidden,
    NotFound,
    TooManyRequests,
    Unprocessable,
)

MAX_RECOVERY_FAILURES = 5
MIN_DEADLINE_SECONDS = 15 * 60
"""A signed move must stay valid this long after it arrives, so that a relayer backlog or a
fee spike cannot make it expire on the way."""
ROTATION_EVENTS = ("RotationRequested", "RotationCancelled", "KeyRotated")
ROTATION_KINDS = ("request_rotation", "cancel_rotation", "finalize_rotation", "rotate_key")
MOVING_KINDS = ("finalize_rotation", "rotate_key")
"""The rotations that change the controller when they land."""
OPEN = (OutboxStatus.PENDING, OutboxStatus.SENDING, OutboxStatus.SENT)
ZERO = "0x" + "00" * 20


@dataclass(frozen=True)
class PendingRotation:
    new_key: str
    ready_at: int
    """Unix time on the chain's clock, after which anyone may finish the rotation."""


def receipt_for(session: Session, project: Project, holder: str, *, lock: bool = False) -> Receipt:
    """The minted receipt of a holder. Locked, two requests to move it run one after another."""
    if not is_address(holder):
        raise BadRequest("bad_holder", "The holder must be an address.")
    query = select(Receipt).where(
        Receipt.project_id == project.id, Receipt.holder == to_checksum_address(holder)
    )
    receipt = session.scalars(query.with_for_update() if lock else query).first()
    if receipt is None or receipt.status != ReceiptStatus.MINTED:
        raise NotFound("no_receipt", "This key has no receipt for this project yet.")
    return receipt


def pending_rotation(contracts: Contracts, receipt: Receipt) -> PendingRotation | None:
    """The requested rotation waiting out its 48 hours, read from the chain itself."""
    new_key, ready_at = contracts.receipts.functions.pendingRotation(int(receipt.token_id)).call()
    if int(new_key, 16) == 0:
        return None
    return PendingRotation(to_checksum_address(new_key), ready_at)


def _open_rows(session: Session, receipt_id: int, kinds: tuple[str, ...]) -> list[ChainOutbox]:
    rows = session.scalars(
        select(ChainOutbox).where(ChainOutbox.kind.in_(kinds), ChainOutbox.status.in_(OPEN))
    )
    return [row for row in rows if int(row.args[0]) == receipt_id]


def in_flight(session: Session, receipt: Receipt, kinds: tuple[str, ...] = ROTATION_KINDS) -> bool:
    """True while a rotation transaction for this receipt is queued or not final yet."""
    return bool(_open_rows(session, int(receipt.token_id), kinds))


def controller_now(contracts: Contracts, project_id: uuid.UUID, holder: str) -> str:
    """The key that controls a holder on-chain at the latest block. Receipt.controller follows
    finalised events, so it lags a rotation by a few blocks; a signature checked against it
    can be accepted here and then revert on-chain."""
    return to_checksum_address(
        contracts.receipts.functions.controllerOf(project_id.bytes, holder).call()
    )


def moving(session: Session, receipt: Receipt) -> bool:
    """True while a rotation that changes the controller is queued or not final yet. Votes and
    choices wait until it is done: one signed by the old key would revert behind it, and one
    signed by the new key would revert before it."""
    return in_flight(session, receipt, MOVING_KINDS)


def chain_time(contracts: Contracts) -> int:
    """The latest block's time: the clock the contracts check deadlines against."""
    return int(contracts.w3.eth.get_block("latest")["timestamp"])


def _new_key(receipt: Receipt, new_key: str) -> str:
    if not is_address(new_key) or int(new_key, 16) == 0:
        raise BadRequest("bad_key", "The new key must be a non-zero address.")
    new_key = to_checksum_address(new_key)
    if new_key == receipt.controller:
        raise Conflict("same_key", "The receipt is already on this key.")
    return new_key


def _not_busy(session: Session, contracts: Contracts, receipt: Receipt) -> None:
    if in_flight(session, receipt) or pending_rotation(contracts, receipt) is not None:
        raise Conflict("rotation_pending", "A move of this receipt is already under way.")


# ---------------------------------------------------------------- with the old key


def rotation_message(
    contracts: Contracts, receipt: Receipt, new_key: str, deadline: int
) -> dict[str, Any]:
    new_key = _new_key(receipt, new_key)
    nonce = contracts.receipts.functions.rotationNonce(int(receipt.token_id)).call()
    return {
        "receiptId": int(receipt.token_id),
        "newKey": new_key,
        "nonce": nonce,
        "deadline": deadline,
    }


def rotate_with_key(
    session: Session,
    domain: eip712.Domain,
    contracts: Contracts,
    receipt: Receipt,
    *,
    new_key: str,
    deadline: int,
    signature: bytes,
) -> ChainOutbox:
    """A donor with their old key moves the receipt to a new one at once.

    This also overrides a pending lost-phone request: rotateBySig clears it on-chain.
    """
    if in_flight(session, receipt):
        raise Conflict("rotation_pending", "A move of this receipt is already under way.")
    if deadline < chain_time(contracts) + MIN_DEADLINE_SECONDS:
        raise Unprocessable(
            "deadline_too_soon",
            "Sign the move with a deadline at least 15 minutes ahead, so that the chain still "
            "takes it when it is sent.",
        )
    message = rotation_message(contracts, receipt, new_key, deadline)
    controller = controller_now(contracts, receipt.project_id, receipt.holder)
    if not eip712.verify(domain, "KeyRotation", message, signature, controller):
        raise Forbidden("bad_signature", "The move is not signed by the receipt's current key.")
    key = f"rotate_key:{receipt.token_id}:{message['nonce']}:{message['newKey']}:{deadline}"
    row = enqueue_again(
        session,
        kind="rotate_key",
        contract="ReceiptToken",
        function="rotateBySig",
        args=[message["receiptId"], message["newKey"], deadline, signature],
        dedupe_key=key,
        project_id=receipt.project_id,
    )
    return require_sent(row, "move")


# ---------------------------------------------------------------- after a lost phone


def request_recovery(
    session: Session,
    contracts: Contracts,
    receipt: Receipt,
    user: User,
    *,
    new_key: str,
    card_last4: str,
) -> ChainOutbox:
    """For a lost phone: queue a rotation that waits 48 hours on-chain.

    The card must be one the account paid with before this receipt was issued, a moment no
    later login can move: someone who took over the phone number cannot pay with a card of
    their own and then name it. Wrong answers are counted on the account's row, locked, so
    answers sent at the same moment all count.
    """
    if holder_owner(session, receipt.holder) != user.id:
        raise Forbidden("not_the_donor", "This receipt does not belong to this account.")
    user = session.get_one(User, user.id, with_for_update=True, populate_existing=True)
    if user.recovery_failures >= MAX_RECOVERY_FAILURES:
        raise TooManyRequests(
            "recovery_locked", "Too many wrong card numbers were tried. Contact Veritas support."
        )
    new_key = _new_key(receipt, new_key)
    _not_busy(session, contracts, receipt)
    paid = select(Donation.card_last4).where(
        Donation.user_id == user.id, Donation.card_last4 == card_last4
    )
    if session.scalars(paid.where(Donation.created_at < receipt.created_at)).first() is None:
        if session.scalars(paid).first() is not None:
            # Not a guess: the account did pay with it, only later. Say so, and count nothing.
            raise Forbidden(
                "card_too_recent",
                "That card was first used after this receipt was issued; name a card the "
                "account paid with before then.",
            )
        user.recovery_failures += 1
        # The wrong answer has to count even though this request fails and rolls back.
        session.commit()
        left = MAX_RECOVERY_FAILURES - user.recovery_failures
        raise Forbidden(
            "card_mismatch",
            f"That is not a card this account paid with. {left} tries left."
            if left
            else "That is not a card this account paid with. Recovery is now locked.",
        )
    user.recovery_failures = 0
    # The receipt row is locked and nothing is under way, so this is the only such request.
    requested = sum(
        1
        for args in session.scalars(
            select(ChainOutbox.args).where(ChainOutbox.kind == "request_rotation")
        )
        if int(args[0]) == int(receipt.token_id)
    )
    return enqueue(
        session,
        kind="request_rotation",
        contract="ReceiptToken",
        function="requestRotation",
        args=[int(receipt.token_id), new_key],
        dedupe_key=f"request_rotation:{receipt.token_id}:{requested + 1}",
        project_id=receipt.project_id,
    )


def _pending_or_404(contracts: Contracts, receipt: Receipt) -> PendingRotation:
    pending = pending_rotation(contracts, receipt)
    if pending is None:
        raise NotFound("no_pending_rotation", "Nobody has asked to move this receipt.")
    return pending


def cancel_message(contracts: Contracts, receipt: Receipt) -> dict[str, Any]:
    """The refusal names the request's readyAt, so it refuses that request and no other."""
    pending = _pending_or_404(contracts, receipt)
    return {
        "receiptId": int(receipt.token_id),
        "newKey": pending.new_key,
        "readyAt": pending.ready_at,
    }


def cancel_rotation(
    session: Session,
    domain: eip712.Domain,
    contracts: Contracts,
    receipt: Receipt,
    signature: bytes,
) -> ChainOutbox:
    """The current key refuses a requested move, for example one made with a stolen number."""
    if in_flight(session, receipt, MOVING_KINDS):
        raise Conflict("rotation_finishing", "This move is already being finished.")
    message = cancel_message(contracts, receipt)
    controller = controller_now(contracts, receipt.project_id, receipt.holder)
    if not eip712.verify(domain, "RotationCancel", message, signature, controller):
        raise Forbidden("bad_signature", "The refusal is not signed by the receipt's current key.")
    row = enqueue_again(
        session,
        kind="cancel_rotation",
        contract="ReceiptToken",
        function="cancelRotation",
        args=[message["receiptId"], signature],
        dedupe_key=f"cancel_rotation:{receipt.token_id}:{message['newKey']}:{message['readyAt']}",
        project_id=receipt.project_id,
    )
    return require_sent(row, "refusal")


def unlock_recovery(session: Session, receipt: Receipt) -> None:
    """Support, having checked who the donor is some other way, allows new tries."""
    owner = holder_owner(session, receipt.holder)
    if owner is not None:
        session.get_one(User, owner).recovery_failures = 0


def finish_rotations(session: Session, contracts: Contracts, now: datetime) -> int:
    """Queues finalizeRotation for every requested rotation whose 48 hours are over, unless
    the old key's refusal or a move with the old key is already on its way."""
    latest: dict[int, ChainEvent] = {}
    for event in session.scalars(
        select(ChainEvent)
        .where(ChainEvent.contract == "ReceiptToken", ChainEvent.event.in_(ROTATION_EVENTS))
        .order_by(ChainEvent.block_number, ChainEvent.log_index)
    ):
        latest[int(event.args["receiptId"])] = event
    queued = 0
    for receipt_id, event in latest.items():
        if event.event != "RotationRequested" or event.args["readyAt"] > now.timestamp():
            continue
        if _open_rows(session, receipt_id, ("cancel_rotation", "rotate_key")):
            continue
        new_key, ready_at = contracts.receipts.functions.pendingRotation(receipt_id).call()
        if new_key != event.args["newKey"] or ready_at != event.args["readyAt"]:
            continue  # cancelled or replaced in a block the indexer has not reached yet
        row = enqueue_again(
            session,
            kind="finalize_rotation",
            contract="ReceiptToken",
            function="finalizeRotation",
            args=[receipt_id],
            dedupe_key=f"finalize_rotation:{event.tx_hash.hex()}:{event.log_index}",
            max_tries=3,
            project_id=event.project_id,
        )
        if row.status == OutboxStatus.PENDING:
            queued += 1
    return queued
