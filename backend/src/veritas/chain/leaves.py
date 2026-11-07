"""Leaf formats shared with the contracts.

There is one donation leaf per donation per milestone. The field order and types
below are the on-chain format: the contracts rebuild the same leaf from calldata
when a donor votes or asks for a refund, so changing anything here is a protocol
change and needs new contracts.
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from eth_utils import is_address, to_checksum_address

from veritas.chain.merkle import StandardMerkleTree, leaf_hash
from veritas.core.money import check_qapik

DONATION_LEAF_TYPES = ("bytes16", "address", "bytes16", "uint8", "uint64", "bytes32", "bytes32")

NO_TRIGGER = bytes(32)
"""Trigger of a normal donation. Pay-on-Proof charges carry the approval's tx hash."""

MAX_MILESTONES = 50


def new_salt() -> bytes:
    return secrets.token_bytes(32)


@dataclass(frozen=True)
class DonationLeaf:
    """The part of one donation that went to one milestone.

    `holder` is the donor's key for this project, not anything that names them.
    `salt` is random and goes only to the donor, so nobody can guess amounts or
    link leaves from the public root. It must be stored the moment it is made.
    """

    donation_id: UUID
    holder: str
    project_id: UUID
    milestone: int
    amount: int
    trigger: bytes = NO_TRIGGER
    salt: bytes = field(default_factory=new_salt)

    def __post_init__(self) -> None:
        if not is_address(self.holder):
            raise ValueError(f"holder is not an address: {self.holder!r}")
        object.__setattr__(self, "holder", to_checksum_address(self.holder))
        if not 0 <= self.milestone < MAX_MILESTONES:
            raise ValueError(f"milestone index out of range: {self.milestone}")
        if check_qapik(self.amount) == 0:
            raise ValueError("a leaf never carries zero qəpik")
        if len(self.trigger) != 32 or len(self.salt) != 32:
            raise ValueError("trigger and salt are 32 bytes each")

    def values(self) -> tuple[Any, ...]:
        return (
            self.donation_id.bytes,
            self.holder,
            self.project_id.bytes,
            self.milestone,
            self.amount,
            self.trigger,
            self.salt,
        )

    def hash(self) -> bytes:
        return leaf_hash(DONATION_LEAF_TYPES, self.values())


def donation_tree(leaves: Sequence[DonationLeaf]) -> StandardMerkleTree:
    """The tree for one hourly batch."""
    return StandardMerkleTree.of([leaf.values() for leaf in leaves], DONATION_LEAF_TYPES)
