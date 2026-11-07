"""Hashes in the shapes the chain and the verifier expect.

Documents and files use SHA-256, so anyone can check them with standard tools.
On-chain structures (Merkle leaves, EIP-712 messages) use keccak256, like Solidity.
Both are 32 bytes and travel as "0x" plus 64 lowercase hex characters.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import BinaryIO

from eth_hash.auto import keccak as _keccak

DIGEST_SIZE = 32

_HEX32 = re.compile(r"0[xX][0-9a-fA-F]{64}")


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def sha256_stream(stream: BinaryIO, chunk_size: int = 1 << 20) -> bytes:
    """SHA-256 of everything left in a binary stream, read in chunks."""
    digest = hashlib.sha256()
    while chunk := stream.read(chunk_size):
        digest.update(chunk)
    return digest.digest()


def sha256_file(path: str | Path) -> bytes:
    with open(path, "rb") as stream:
        return sha256_stream(stream)


def keccak256(data: bytes) -> bytes:
    return _keccak(data)


def to_hex(digest: bytes) -> str:
    """32 bytes to "0x" plus 64 lowercase hex characters."""
    if len(digest) != DIGEST_SIZE:
        raise ValueError(f"expected {DIGEST_SIZE} bytes, got {len(digest)}")
    return "0x" + digest.hex()


def from_hex(text: str) -> bytes:
    """The reverse of to_hex. Upper and lower case digits are both fine."""
    if not isinstance(text, str) or not _HEX32.fullmatch(text):
        raise ValueError(f"expected 0x and 64 hex characters: {text!r}")
    return bytes.fromhex(text[2:])
