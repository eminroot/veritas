import re
from pathlib import Path

import pytest
from eth_account import Account
from eth_account.messages import _hash_eip191_message, encode_typed_data

from veritas.chain.eip712 import (
    MESSAGE_TYPES,
    Domain,
    EIP712Error,
    digest,
    recover,
    sign,
    struct_hash,
    type_string,
    typed_data,
    verify,
)

SOLIDITY_TYPES = Path(__file__).parents[2] / "contracts" / "src" / "libraries" / "VeritasTypes.sol"
KEY = bytes.fromhex("8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba")
SIGNER = "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc"
DOMAIN = Domain(31337, "0x000000000000000000000000000000000000bEEF")
SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def sample(kind):
    if kind == "string":
        return "bafkreigh2akiscaildcqabsyg3dfr6chu3fgpregiymsck7e7aqa4s52zy"
    if kind == "address":
        return "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
    if kind == "bool":
        return True
    if kind.startswith("bytes"):
        return bytes(range(int(kind[5:])))
    return 7


def sample_message(primary):
    return {name: sample(kind) for name, kind in MESSAGE_TYPES[primary]}


def test_type_strings_match_the_contracts():
    if not SOLIDITY_TYPES.exists():
        pytest.skip("contracts are not checked out next to the backend")
    source = re.sub(r'"\s*\n\s*"', "", SOLIDITY_TYPES.read_text(encoding="utf-8"))
    declared = set(re.findall(r'keccak256\(\s*"([A-Za-z]+\([^"]*\))"', source))
    assert declared == {type_string(primary) for primary in MESSAGE_TYPES}


@pytest.mark.parametrize("primary", sorted(MESSAGE_TYPES))
def test_digest_matches_eth_account(primary):
    message = sample_message(primary)
    full = typed_data(DOMAIN, primary, message)
    assert digest(DOMAIN, primary, message) == _hash_eip191_message(
        encode_typed_data(full_message=full)
    )


@pytest.mark.parametrize("primary", sorted(MESSAGE_TYPES))
def test_sign_and_recover(primary):
    message = sample_message(primary)
    signature = sign(KEY, DOMAIN, primary, message)
    assert len(signature) == 65 and signature[64] in (27, 28)
    assert int.from_bytes(signature[32:64], "big") <= SECP256K1_N // 2  # OpenZeppelin wants low s
    assert recover(DOMAIN, primary, message, signature) == SIGNER
    assert verify(DOMAIN, primary, message, signature, SIGNER.lower())


def test_any_change_breaks_the_signature():
    message = sample_message("Vote")
    signature = sign(KEY, DOMAIN, "Vote", message)
    assert not verify(DOMAIN, "Vote", message | {"approve": False}, signature, SIGNER)
    assert not verify(Domain(1, DOMAIN.verifying_contract), "Vote", message, signature, SIGNER)
    assert not verify(DOMAIN, "Vote", message, signature[:64] + b"\x05", SIGNER)
    assert not verify(DOMAIN, "Vote", message, b"\x00" * 65, SIGNER)


def test_domain_separator_matches_eth_account():
    full = typed_data(DOMAIN, "Withdraw", sample_message("Withdraw"))
    assert encode_typed_data(full_message=full).header == DOMAIN.separator()


@pytest.mark.parametrize(
    "change",
    [
        {"projectId": b"\x01" * 15},
        {"milestone": "1"},
        {"approve": 1},
        {"holder": "0x1234"},
        {"round": True},
    ],
)
def test_values_must_fit_their_types(change):
    with pytest.raises(EIP712Error):
        struct_hash("Vote", sample_message("Vote") | change)


def test_fields_must_be_exact():
    message = sample_message("Withdraw")
    with pytest.raises(EIP712Error):
        struct_hash("Withdraw", message | {"extra": 1})
    with pytest.raises(EIP712Error):
        struct_hash("Withdraw", {"projectId": message["projectId"]})


def test_big_integers_reach_the_app_as_strings():
    """A receipt id is 256 bits; as a JSON number, JavaScript would round it."""
    message = sample_message("KeyRotation") | {"receiptId": 2**255 + 1}
    full = typed_data(DOMAIN, "KeyRotation", message)
    assert full["message"]["receiptId"] == str(2**255 + 1)
    assert full["message"]["nonce"] == 7
    signed = Account.sign_typed_data(KEY, full_message=full)
    assert bytes(signed.signature) == sign(KEY, DOMAIN, "KeyRotation", message)


@pytest.mark.parametrize("primary", sorted(MESSAGE_TYPES))
def test_the_json_the_app_signs_gives_the_same_signature(primary):
    """The app signs the typed-data JSON the API hands it; a wallet library must end up with
    exactly the signature the backend makes from the same message."""
    message = sample_message(primary)
    full = typed_data(DOMAIN, primary, message)
    signed = Account.sign_typed_data(KEY, full_message=full)
    assert bytes(signed.signature) == sign(KEY, DOMAIN, primary, message)
