"""A donor's leaves and Merkle proofs, the way votes and claims hand them to the contracts.

The contracts accept only leaves from settled batches. Votes want them in strictly
increasing leaf-hash order, so none counts twice; claims mark each leaf as used. The number of
eligible voters, which Veritas claims when it opens a vote, comes from the same rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from veritas.core.hashing import from_hex
from veritas.db.models.money import Allocation, AllocationStatus, BatchLeaf


@dataclass(frozen=True)
class LeafProof:
    allocation_id: uuid.UUID
    batch_id: int
    leaf: tuple[Any, ...]
    proof: tuple[bytes, ...]
    leaf_hash: bytes
    amount: int
    milestone: int

    def abi_value(self) -> tuple[Any, ...]:
        """The LeafProof struct for web3: (batchId, leaf, proof)."""
        return (self.batch_id, self.leaf, list(self.proof))


def holder_leaves(
    session: Session,
    project_id: uuid.UUID,
    holder: str,
    *,
    milestone: int | None = None,
    status: str = AllocationStatus.IN_ESCROW,
) -> list[LeafProof]:
    query = (
        select(Allocation, BatchLeaf)
        .join(BatchLeaf, BatchLeaf.allocation_id == Allocation.id)
        .where(
            Allocation.project_id == project_id,
            Allocation.holder == holder,
            Allocation.status == status,
        )
    )
    if milestone is not None:
        query = query.where(Allocation.milestone_index == milestone)
    items = [
        LeafProof(
            allocation_id=allocation.id,
            batch_id=leaf.batch_id,
            leaf=(
                allocation.donation_id.bytes,
                allocation.holder,
                allocation.project_id.bytes,
                allocation.milestone_index,
                allocation.amount_qapik,
                allocation.trigger,
                allocation.salt,
            ),
            proof=tuple(from_hex(node) for node in leaf.proof),
            leaf_hash=allocation.leaf_hash,
            amount=allocation.amount_qapik,
            milestone=allocation.milestone_index,
        )
        for allocation, leaf in session.execute(query).all()
    ]
    return sorted(items, key=lambda item: item.leaf_hash)


def eligible_voters(
    session: Session, project_id: uuid.UUID, min_amount: int, milestone: int | None = None
) -> int:
    """Donors whose leaves in escrow add up to the Passport's minimum: for one milestone, or
    for the whole project in an amendment or stop vote."""
    query = select(Allocation.holder).where(
        Allocation.project_id == project_id,
        Allocation.status == AllocationStatus.IN_ESCROW,
    )
    if milestone is not None:
        query = query.where(Allocation.milestone_index == milestone)
    grouped = (
        query.group_by(Allocation.holder)
        .having(func.sum(Allocation.amount_qapik) >= min_amount)
        .subquery()
    )
    return int(session.scalar(select(func.count()).select_from(grouped)) or 0)
