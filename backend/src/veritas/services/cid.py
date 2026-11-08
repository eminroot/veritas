"""IPFS content identifiers for published bytes, computed without an IPFS node.

A CIDv1 with the raw codec (0x55) and a SHA-256 multihash, written in lower-case
base32 with the multibase prefix "b". It is what `ipfs block put` returns for the
same bytes, and what `ipfs add --cid-version 1 --raw-leaves` returns for a file
that fits in one chunk (256 KiB by default; a Passport is a few KB). The real IPFS
upload replaces this in a later phase and must give the same CID.
"""

from __future__ import annotations

import base64

from veritas.core.hashing import sha256

CID_VERSION = 0x01
RAW_CODEC = 0x55
SHA2_256 = 0x12


def raw_cid(data: bytes) -> str:
    digest = sha256(data)
    # Every number here is below 0x80, so each varint is a single byte.
    cid = bytes([CID_VERSION, RAW_CODEC, SHA2_256, len(digest)]) + digest
    return "b" + base64.b32encode(cid).decode("ascii").lower().rstrip("=")
