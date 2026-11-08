"""Receipt token ids, as ReceiptToken.receiptId computes them."""

from __future__ import annotations

import uuid

from eth_abi import encode
from eth_utils import to_checksum_address

from veritas.core.hashing import keccak256


def receipt_id(project_id: uuid.UUID, holder: str) -> int:
    """uint256(keccak256(abi.encode(projectId, holder))): one receipt per donor key per project."""
    encoded = encode(["bytes16", "address"], [project_id.bytes, to_checksum_address(holder)])
    return int.from_bytes(keccak256(encoded), "big")
