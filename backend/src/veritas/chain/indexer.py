"""The indexer: contract events from finalised blocks into PostgreSQL.

It reads only blocks the chain will not take back, a chunk at a time, from every Veritas
address it knows: the system contracts and each project's escrow, found through the factory's
ProjectCreated events. Each event is stored once in `chain_events` and handed to the
handlers registered for it, in chain order, inside the same transaction that moves the
cursor. A crash part way through a chunk therefore repeats the chunk, and storing is
idempotent, so nothing is lost or applied twice.

When a confirmed outbox transaction did not emit the event its kind promised, or an event
names something the database does not know, the indexer raises an alert.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from eth_utils import to_checksum_address
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker
from web3 import Web3

from veritas.chain.alerts import raise_alert
from veritas.chain.codec import EventDecoder
from veritas.chain.contracts import SYSTEM, Contracts
from veritas.chain.relayer import final_block
from veritas.db.models.chain import (
    ChainContract,
    ChainCursor,
    ChainEvent,
    ChainOutbox,
    OutboxStatus,
)
from veritas.db.session import db_now

log = logging.getLogger(__name__)

Handler = Callable[[Session, ChainEvent], None]

ESCROW = "MilestoneEscrow"


@dataclass(frozen=True)
class IndexerConfig:
    name: str = "main"
    chunk: int = 2_000
    confirmations: int | None = None
    """None: read up to the node's "finalized" block. A number: that many blocks behind."""


@dataclass
class Handlers:
    """What to do with each event. Later phases register more."""

    by_event: dict[tuple[str, str], list[Handler]] = field(default_factory=dict)
    expected: dict[str, tuple[str, str]] = field(default_factory=dict)
    """Outbox kind -> the (contract, event) its transaction must emit."""

    def on(self, contract: str, event: str) -> Callable[[Handler], Handler]:
        def register(handler: Handler) -> Handler:
            self.by_event.setdefault((contract, event), []).append(handler)
            return handler

        return register

    def expect(self, kind: str, contract: str, event: str) -> None:
        self.expected[kind] = (contract, event)

    def dispatch(self, session: Session, event: ChainEvent) -> None:
        for handler in self.by_event.get((event.contract, event.event), []):
            handler(session, event)


def _project_id(args: Mapping[str, Any]) -> uuid.UUID | None:
    value = args.get("projectId")
    return uuid.UUID(hex=value[2:]) if isinstance(value, str) and len(value) == 34 else None


class Indexer:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        contracts: Contracts,
        handlers: Handlers,
        config: IndexerConfig | None = None,
    ) -> None:
        self.sessions = sessions
        self.contracts = contracts
        self.w3: Web3 = contracts.w3
        self.handlers = handlers
        self.config = config or IndexerConfig()
        self.decoder = EventDecoder(self.w3, SYSTEM)

    def bootstrap(self, session: Session) -> ChainCursor:
        """Registers the system contracts and puts the cursor just before the deployment."""
        deployment = self.contracts.deployment
        for name, address in deployment.addresses.items():
            if name == ESCROW:
                continue  # the implementation never emits project events itself
            session.execute(
                insert(ChainContract)
                .values(address=address, contract=name, from_block=deployment.start_block)
                .on_conflict_do_nothing(index_elements=["address"])
            )
        cursor = session.get(ChainCursor, self.config.name, with_for_update=True)
        if cursor is None:
            cursor = ChainCursor(name=self.config.name, block_number=deployment.start_block - 1)
            session.add(cursor)
            session.flush()
        return cursor

    def run_once(self) -> int:
        """Indexes one chunk of finalised blocks. Returns how many new events it stored."""
        with self.sessions() as session:
            cursor = self.bootstrap(session)
            head = final_block(self.w3, self.config.confirmations)
            if cursor.block_number >= head:
                session.commit()
                return 0
            start = cursor.block_number + 1
            end = min(head, cursor.block_number + self.config.chunk)
            stored = self._index(session, start, end)
            cursor.block_number = end
            self._check_expectations(session, end)
            session.commit()
            if stored:
                log.info("indexed %s events in blocks %s-%s", stored, start, end)
            return stored

    def catch_up(self, max_rounds: int = 1_000) -> int:
        total = 0
        for _ in range(max_rounds):
            before = self._cursor_block()
            total += self.run_once()
            if self._cursor_block() == before:
                break
        return total

    def _cursor_block(self) -> int:
        with self.sessions() as session:
            cursor = session.get(ChainCursor, self.config.name)
            return cursor.block_number if cursor else -1

    # ------------------------------------------------------------------ internals

    def _logs(self, addresses: Iterable[str], start: int, end: int) -> list[Any]:
        addresses = sorted(set(addresses))
        if not addresses:
            return []
        return list(
            self.w3.eth.get_logs({"address": addresses, "fromBlock": start, "toBlock": end})
        )

    def _index(self, session: Session, start: int, end: int) -> int:
        known = {
            row.address: row
            for row in session.scalars(select(ChainContract).where(ChainContract.from_block <= end))
        }
        names = {address: row.contract for address, row in known.items()}
        system = [a for a, row in known.items() if row.contract != ESCROW]
        logs = self._logs(system, start, end)

        # Escrows created in this chunk emit events in it too: find them before fetching.
        for raw in logs:
            address = to_checksum_address(raw["address"])
            decoded = self.decoder.decode(names.get(address, ""), raw)
            if decoded and decoded[0] == "ProjectCreated":
                names[to_checksum_address(decoded[1]["escrow"])] = ESCROW
        escrows = [address for address, name in names.items() if name == ESCROW]
        logs += self._logs(escrows, start, end)
        logs.sort(key=lambda item: (item["blockNumber"], item["logIndex"]))

        stored = 0
        for raw in logs:
            address = to_checksum_address(raw["address"])
            contract = names.get(address)
            decoded = self.decoder.decode(contract, raw) if contract else None
            if decoded is None:
                continue
            name, args = decoded
            project = _project_id(args)
            if project is None and contract == ESCROW and address in known:
                project = known[address].project_id
            row = session.scalars(
                insert(ChainEvent)
                .values(
                    block_number=raw["blockNumber"],
                    block_hash=bytes(raw["blockHash"]),
                    tx_hash=bytes(raw["transactionHash"]),
                    log_index=raw["logIndex"],
                    address=address,
                    contract=contract,
                    event=name,
                    args=args,
                    project_id=project,
                )
                .on_conflict_do_nothing(index_elements=["tx_hash", "log_index"])
                .returning(ChainEvent)
            ).first()
            if row is None:
                continue  # stored by an earlier run that did not finish the chunk
            stored += 1
            if name == "ProjectCreated":
                self._watch_escrow(session, args, raw["blockNumber"], known)
            self.handlers.dispatch(session, row)
        return stored

    def _watch_escrow(
        self,
        session: Session,
        args: Mapping[str, Any],
        block: int,
        known: dict[str, ChainContract],
    ) -> None:
        address = to_checksum_address(args["escrow"])
        project = _project_id(args)
        from veritas.db.models import Project  # here, so chain code does not import the API layer

        if project is not None and session.get(Project, project) is None:
            project = None  # launched outside this database; still indexed, with an alert
            raise_alert(
                session,
                kind="unknown_project",
                message=f"a project this database does not know was launched at {address}",
                details={"escrow": address, "projectId": args.get("projectId")},
                dedupe_key=f"unknown_project:{address}",
            )
        session.execute(
            insert(ChainContract)
            .values(address=address, contract=ESCROW, project_id=project, from_block=block)
            .on_conflict_do_nothing(index_elements=["address"])
        )
        known[address] = ChainContract(
            address=address, contract=ESCROW, project_id=project, from_block=block
        )

    def _check_expectations(self, session: Session, indexed_to: int) -> None:
        """Every confirmed outbox transaction in indexed blocks emitted what its kind promised."""
        rows = session.scalars(
            select(ChainOutbox).where(
                ChainOutbox.status == OutboxStatus.CONFIRMED,
                ChainOutbox.mined_block <= indexed_to,
                ChainOutbox.events_checked_at.is_(None),
            )
        ).all()
        now = db_now(session)
        for row in rows:
            row.events_checked_at = now
            if row.kind not in self.handlers.expected:
                continue
            contract, event = self.handlers.expected[row.kind]
            found = session.scalar(
                select(ChainEvent.id).where(
                    ChainEvent.tx_hash == row.tx_hash,
                    ChainEvent.contract == contract,
                    ChainEvent.event == event,
                )
            )
            if found is None:
                raise_alert(
                    session,
                    kind="expected_event_missing",
                    severity="critical",
                    message=f"outbox {row.id} ({row.kind}) confirmed without {contract}.{event}",
                    details={"outbox_id": row.id, "tx_hash": "0x" + row.tx_hash.hex()},
                    dedupe_key=f"expected_event_missing:{row.id}",
                )
