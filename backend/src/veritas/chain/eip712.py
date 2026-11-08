"""EIP-712 messages shared with the contracts.

Every party signs its own actions: the charity its Passport and evidence, the officer a
decision, a donor a vote or a refund choice, the bank its attestations. All of them are
EIP-712 messages in one domain: name "Veritas", version "1", the chain id and the address of
the VeritasHub. The type strings below are the protocol. `VeritasTypes.sol` declares the same
ones, and `scripts/make_contract_vectors.py` signs a whole milestone here that the Foundry
tests then replay on-chain, so the two sides cannot drift apart unnoticed.

Values use Python types: bytesN as bytes of exactly N, addresses as hex strings, integers as
int, strings as str and arrays as sequences.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from eth_abi import encode
from eth_keys import keys
from eth_utils import is_address, to_checksum_address

from veritas.core.hashing import keccak256

DOMAIN_NAME = "Veritas"
DOMAIN_VERSION = "1"

DOMAIN_FIELDS = (
    ("name", "string"),
    ("version", "string"),
    ("chainId", "uint256"),
    ("verifyingContract", "address"),
)

MESSAGE_TYPES: dict[str, tuple[tuple[str, str], ...]] = {
    # The charity launches a project: the Passport hash, where to fetch it, and the hash of
    # the on-chain config derived from it (veritas.chain.project.ProjectConfig).
    "ProjectLaunch": (
        ("projectId", "bytes16"),
        ("version", "uint32"),
        ("passportHash", "bytes32"),
        ("cid", "string"),
        ("configHash", "bytes32"),
    ),
    "Evidence": (
        ("projectId", "bytes16"),
        ("milestone", "uint8"),
        ("attempt", "uint32"),
        ("bundleHash", "bytes32"),
    ),
    "Decision": (
        ("projectId", "bytes16"),
        ("milestone", "uint8"),
        ("attempt", "uint32"),
        ("approve", "bool"),
        ("bundleHash", "bytes32"),
        ("reportHash", "bytes32"),
        ("invoiceHash", "bytes32"),
        ("amount", "uint64"),
        ("overrideChecks", "bool"),
        ("reasonHash", "bytes32"),
    ),
    "Vote": (
        ("projectId", "bytes16"),
        ("holder", "address"),
        ("kind", "uint8"),
        ("milestone", "uint8"),
        ("round", "uint32"),
        ("approve", "bool"),
    ),
    "Choice": (
        ("projectId", "bytes16"),
        ("holder", "address"),
        ("action", "uint8"),
        ("target", "address"),
        ("nonce", "uint32"),
        ("deadline", "uint64"),
    ),
    "Withdraw": (("projectId", "bytes16"), ("reasonHash", "bytes32")),
    "StopProposal": (("projectId", "bytes16"), ("round", "uint32"), ("reasonHash", "bytes32")),
    "Amendment": (
        ("projectId", "bytes16"),
        ("version", "uint32"),
        ("passportHash", "bytes32"),
        ("cid", "string"),
        ("contractorHash", "bytes32"),
    ),
    "Completion": (("projectId", "bytes16"), ("reportHash", "bytes32"), ("cid", "string")),
    "BatchAttestation": (
        ("batchId", "uint64"),
        ("root", "bytes32"),
        ("leafCount", "uint32"),
        ("total", "uint64"),
        ("creditsHash", "bytes32"),
    ),
    "Settlement": (("batchId", "uint64"), ("creditsHash", "bytes32")),
    "BalanceAttestation": (
        ("day", "uint64"),
        ("cutoffBlock", "uint64"),
        ("cutoffTime", "uint64"),
        ("balance", "uint64"),
        ("statementHash", "bytes32"),
    ),
    "PayoutConfirmation": (
        ("instructionId", "uint64"),
        ("amount", "uint64"),
        ("paymentRef", "bytes32"),
    ),
    "PayoutFailure": (("instructionId", "uint64"), ("reasonHash", "bytes32")),
    "KeyRotation": (
        ("receiptId", "uint256"),
        ("newKey", "address"),
        ("nonce", "uint64"),
        ("deadline", "uint64"),
    ),
    "RotationCancel": (("receiptId", "uint256"), ("newKey", "address"), ("readyAt", "uint64")),
}

# Ballot kinds and claim actions, as in VeritasTypes.sol.
BALLOT_MILESTONE = 0
BALLOT_AMENDMENT = 1
BALLOT_STOP = 2
CHOICE_REFUND = 1
CHOICE_REDIRECT = 2


class EIP712Error(ValueError):
    """A message that does not fit its type, or a signature that does not check out."""


def type_string(primary: str, fields: Sequence[tuple[str, str]] | None = None) -> str:
    fields = MESSAGE_TYPES[primary] if fields is None else fields
    return f"{primary}({','.join(f'{kind} {name}' for name, kind in fields)})"


def type_hash(primary: str) -> bytes:
    return keccak256(type_string(primary).encode())


def _encode_value(kind: str, value: Any) -> bytes:
    if kind == "string":
        if not isinstance(value, str):
            raise EIP712Error(f"expected a str, got {value!r}")
        return keccak256(value.encode("utf-8"))
    if kind == "bytes":
        return keccak256(bytes(value))
    if kind.endswith("[]"):
        return keccak256(b"".join(_encode_value(kind[:-2], item) for item in value))
    if kind.startswith("bytes") and (not isinstance(value, bytes) or len(value) != int(kind[5:])):
        raise EIP712Error(f"{kind} needs exactly {kind[5:]} bytes, got {value!r}")
    if kind == "address" and not is_address(value):
        raise EIP712Error(f"not an address: {value!r}")
    if kind.startswith(("uint", "int")) and (isinstance(value, bool) or not isinstance(value, int)):
        raise EIP712Error(f"{kind} needs an int, got {value!r}")
    if kind == "bool" and not isinstance(value, bool):
        raise EIP712Error(f"bool needs a bool, got {value!r}")
    return encode([kind], [value])


def struct_hash(primary: str, message: Mapping[str, Any]) -> bytes:
    fields = MESSAGE_TYPES[primary]
    if set(message) != {name for name, _ in fields}:
        raise EIP712Error(f"{primary} has fields {[n for n, _ in fields]}, got {sorted(message)}")
    encoded = b"".join(_encode_value(kind, message[name]) for name, kind in fields)
    return keccak256(type_hash(primary) + encoded)


@dataclass(frozen=True)
class Domain:
    chain_id: int
    verifying_contract: str

    def __post_init__(self) -> None:
        if not is_address(self.verifying_contract):
            raise EIP712Error(f"not an address: {self.verifying_contract!r}")
        object.__setattr__(self, "verifying_contract", to_checksum_address(self.verifying_contract))

    def separator(self) -> bytes:
        values = (DOMAIN_NAME, DOMAIN_VERSION, self.chain_id, self.verifying_contract)
        kinds = [kind for _, kind in DOMAIN_FIELDS]
        encoded = b"".join(map(_encode_value, kinds, values))
        return keccak256(keccak256(type_string("EIP712Domain", DOMAIN_FIELDS).encode()) + encoded)

    def as_json(self) -> dict[str, Any]:
        return {
            "name": DOMAIN_NAME,
            "version": DOMAIN_VERSION,
            "chainId": self.chain_id,
            "verifyingContract": self.verifying_contract,
        }


def digest(domain: Domain, primary: str, message: Mapping[str, Any]) -> bytes:
    """The 32 bytes that get signed: keccak256(0x1901 || domainSeparator || structHash)."""
    return keccak256(b"\x19\x01" + domain.separator() + struct_hash(primary, message))


def sign(private_key: bytes, domain: Domain, primary: str, message: Mapping[str, Any]) -> bytes:
    """A 65-byte r || s || v signature (v is 27 or 28, s is low), as OpenZeppelin's ECDSA wants."""
    signed = keys.PrivateKey(private_key).sign_msg_hash(digest(domain, primary, message))
    return signed.r.to_bytes(32, "big") + signed.s.to_bytes(32, "big") + bytes([signed.v + 27])


SECP256K1_HALF_N = 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0
"""OpenZeppelin's ECDSA refuses an s above this (the high-s twin of a valid signature)."""


def recover(domain: Domain, primary: str, message: Mapping[str, Any], signature: bytes) -> str:
    """The checksummed address that made a 65-byte signature.

    Only what OpenZeppelin's ECDSA.recover accepts: v of 27 or 28 and a low s. The high-s twin
    of a valid signature recovers the same key here but reverts on-chain.
    """
    if len(signature) != 65 or signature[64] not in (27, 28):
        raise EIP712Error("expected a 65-byte signature with v of 27 or 28")
    if int.from_bytes(signature[32:64], "big") > SECP256K1_HALF_N:
        raise EIP712Error("s is in the upper half of the curve order, which the contracts refuse")
    vrs = signature[:64] + bytes([signature[64] - 27])
    try:
        public_key = keys.Signature(vrs).recover_public_key_from_msg_hash(
            digest(domain, primary, message)
        )
    except Exception as exc:  # eth_keys raises several kinds of errors for bad points
        raise EIP712Error(f"cannot recover a key from this signature: {exc}") from exc
    return public_key.to_checksum_address()


def verify(
    domain: Domain, primary: str, message: Mapping[str, Any], signature: bytes, signer: str
) -> bool:
    """True if the key `signer` signed the message. A key only: a contract signer (a Safe,
    through ERC-1271) needs the chain, see `veritas.chain.signatures`."""
    try:
        return recover(domain, primary, message, signature) == to_checksum_address(signer)
    except EIP712Error:
        return False


JS_SAFE_INTEGER = 2**53 - 1


def _json_value(kind: str, value: Any) -> Any:
    if kind.endswith("[]"):
        return [_json_value(kind[:-2], item) for item in value]
    if kind.startswith("bytes"):
        return "0x" + bytes(value).hex()
    if kind == "address":
        return to_checksum_address(value)
    if kind.startswith(("uint", "int")) and abs(value) > JS_SAFE_INTEGER:
        return str(value)
    return value


def typed_data(domain: Domain, primary: str, message: Mapping[str, Any]) -> dict[str, Any]:
    """The eth_signTypedData_v4 JSON the app signs, with bytes as 0x hex.

    Integers a JavaScript number cannot hold exactly, like receipt ids, are decimal strings,
    which wallet libraries accept for integer fields.
    """
    fields = MESSAGE_TYPES[primary]
    return {
        "types": {
            "EIP712Domain": [{"name": n, "type": t} for n, t in DOMAIN_FIELDS],
            primary: [{"name": n, "type": t} for n, t in fields],
        },
        "domain": domain.as_json(),
        "primaryType": primary,
        "message": {name: _json_value(kind, message[name]) for name, kind in fields},
    }
