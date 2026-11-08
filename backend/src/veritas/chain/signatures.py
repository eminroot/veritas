"""Checking a party's signature exactly as the contracts do (libraries/Signatures.sol).

The contracts use OpenZeppelin's SignatureChecker. An address without code is a key: the
signature must be ECDSA with a low s (`eip712.verify`). An address with code is a contract,
such as an officer's or a charity's Safe multisig: it is asked through ERC-1271 whether it
signed the message's EIP-712 digest. Checking only keys here would refuse every Safe
signature the chain takes; accepting what the chain refuses would queue calls that revert.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from eth_abi import encode
from eth_utils import to_checksum_address
from web3 import Web3

from veritas.chain import eip712

ERC1271_SELECTOR = bytes.fromhex("1626ba7e")
"""isValidSignature(bytes32,bytes): the call, and the answer that means yes."""

STATIC_CALLER = "0x0000000000000000000000000000000000001271"
"""An address that only exists inside the eth_call below, through a state override."""
STATIC_CALLER_CODE = (
    "0x60203603806020600037600060008260006000355afa3d600060003e3d60009160255790fd5b90f3"
)
"""STATICCALLs the address in the first 32 bytes of its calldata with the rest, and returns
or reverts with what it got back. OpenZeppelin asks the signer with STATICCALL, so a wallet
that writes state while answering is refused on-chain; a plain eth_call would accept it."""


def signed_by(
    w3: Web3,
    domain: eip712.Domain,
    primary: str,
    message: Mapping[str, Any],
    signature: bytes,
    signer: str | None,
) -> bool:
    """True if `signer` signed the message, by the contracts' rules, at the latest block."""
    if not signer or int(signer, 16) == 0:
        return False
    signer = to_checksum_address(signer)
    if not w3.eth.get_code(signer):
        return eip712.verify(domain, primary, message, signature, signer)
    data = ERC1271_SELECTOR + encode(
        ["bytes32", "bytes"], [eip712.digest(domain, primary, message), signature]
    )
    target = bytes(12) + bytes.fromhex(signer[2:])
    try:
        answer = bytes(
            w3.eth.call(
                {"to": STATIC_CALLER, "data": "0x" + (target + data).hex()},
                "latest",
                {STATIC_CALLER: {"code": STATIC_CALLER_CODE}},
            )
        )
    except Exception:  # a revert, or a contract without the function: not signed
        return False
    return len(answer) >= 32 and answer[:32] == ERC1271_SELECTOR.ljust(32, b"\0")
