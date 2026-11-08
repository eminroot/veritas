"""Writing chain calls into the outbox.

Call `enqueue` inside the same transaction as the business change. If that transaction
commits, the relayer will send the call exactly once; if it rolls back, the call never
existed. The dedupe key makes enqueueing idempotent: the same key gives back the first row.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from functools import cache
from typing import Any

from eth_abi import decode
from eth_utils import keccak
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from veritas.chain.codec import encode_args
from veritas.chain.contracts import ARTIFACTS, abi
from veritas.db.models.chain import ChainOutbox, OutboxStatus, Sender
from veritas.services.errors import Conflict


def enqueue(
    session: Session,
    *,
    kind: str,
    contract: str,
    function: str,
    args: Sequence[Any],
    dedupe_key: str,
    address: str | None = None,
    sender: Sender = Sender.RELAYER,
    project_id: uuid.UUID | None = None,
) -> ChainOutbox:
    values = {
        "kind": kind,
        "dedupe_key": dedupe_key,
        "contract": contract,
        "address": address,
        "function": function,
        "args": encode_args(contract, function, args),
        "sender": str(sender),
        "status": str(OutboxStatus.PENDING),
        "project_id": project_id,
    }
    session.execute(
        insert(ChainOutbox).values(**values).on_conflict_do_nothing(index_elements=["dedupe_key"])
    )
    return session.scalars(select(ChainOutbox).where(ChainOutbox.dedupe_key == dedupe_key)).one()


def enqueue_again(
    session: Session, *, dedupe_key: str, max_tries: int = 5, **call: Any
) -> ChainOutbox:
    """`enqueue`, except that a key whose row failed gets a new row, up to `max_tries` rows.

    The relayer never retries a failed row, and a person signing the same message again (an
    ECDSA signature over the same message is the same bytes) would otherwise get the failed
    row back and nothing sent. The retries are `key:2`, `key:3`, ...; a row that is queued,
    on its way or confirmed is returned as it is, so this stays idempotent. After `max_tries`
    failures the last failed row is returned: something needs a person, and the relayer has
    raised an alert for each failure.
    """
    tries = session.scalars(
        select(ChainOutbox).where(
            (ChainOutbox.dedupe_key == dedupe_key)
            | ChainOutbox.dedupe_key.startswith(dedupe_key + ":", autoescape=True)
        )
    ).all()
    latest = max(tries, key=lambda row: row.id, default=None)
    if latest is not None and (latest.status != OutboxStatus.FAILED or len(tries) >= max_tries):
        return latest
    key = dedupe_key if latest is None else f"{dedupe_key}:{len(tries) + 1}"
    return enqueue(session, dedupe_key=key, **call)


def failed_reason(row: ChainOutbox) -> str:
    """Why the chain refused a row: the contract's error by name, like BadSignature(0x90F7...),
    when the revert data names one, or the relayer's own words."""
    text = (row.last_error or "the chain refused it").splitlines()[0]
    found = re.search(r"0x([0-9a-fA-F]{8,})", text)
    if found:
        named = _named_error(bytes.fromhex(found.group(1)[: len(found.group(1)) // 2 * 2]))
        if named is not None:
            return named
    return text[:200]


def require_sent(row: ChainOutbox, what: str) -> ChainOutbox:
    """The row `enqueue_again` gave back, if it is going out. When the retries are used up it
    is the last failed row; refuse then, with the chain's reason, instead of answering that
    something was queued when nothing will be sent."""
    if row.status == OutboxStatus.FAILED:
        raise Conflict(
            "refused_on_chain",
            f"The chain refused this {what} each time it was sent; the last reason was "
            f"{failed_reason(row)}. Veritas support has been alerted.",
        )
    return row


@cache
def _errors() -> dict[bytes, tuple[str, tuple[str, ...]]]:
    """Every custom error of the Veritas contracts, by selector."""
    found: dict[bytes, tuple[str, tuple[str, ...]]] = {}
    for path in ARTIFACTS.glob("*.json"):
        for entry in abi(path.stem):
            if entry.get("type") == "error":
                types = tuple(arg["type"] for arg in entry.get("inputs", []))
                selector = keccak(text=f"{entry['name']}({','.join(types)})")[:4]
                found[selector] = (entry["name"], types)
    return found


def _named_error(data: bytes) -> str | None:
    known = _errors().get(data[:4])
    if known is None:
        return None
    name, types = known
    try:
        values = decode(list(types), data[4:]) if types else ()
    except Exception:  # truncated or odd revert data: the name alone still helps
        return name
    shown = ["0x" + v.hex() if isinstance(v, bytes) else str(v) for v in values]
    return f"{name}({', '.join(shown)})" if shown else name
