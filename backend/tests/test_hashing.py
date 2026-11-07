import io

import pytest

from veritas.core.hashing import from_hex, keccak256, sha256, sha256_file, sha256_stream, to_hex

ABC_SHA256 = "0xba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
EMPTY_KECCAK = "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
ABC_KECCAK = "0x4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"


def test_known_digests():
    assert to_hex(sha256(b"abc")) == ABC_SHA256
    assert to_hex(keccak256(b"")) == EMPTY_KECCAK
    assert to_hex(keccak256(b"abc")) == ABC_KECCAK


def test_stream_and_file_match_one_shot(tmp_path):
    data = bytes(range(256)) * 5_000
    path = tmp_path / "evidence.bin"
    path.write_bytes(data)
    assert sha256_file(path) == sha256(data)
    assert sha256_stream(io.BytesIO(data), chunk_size=7) == sha256(data)
    assert sha256_stream(io.BytesIO(b"")) == sha256(b"")


def test_hex_round_trip():
    digest = sha256(b"veritas")
    assert from_hex(to_hex(digest)) == digest
    assert from_hex("0X" + digest.hex().upper()) == digest


@pytest.mark.parametrize(
    "bad",
    ["", "0x", "0x" + "g" * 64, "ab" * 32, "0x" + "ab" * 31, "0x" + "ab " * 21 + "a", None, 5],
)
def test_from_hex_rejects(bad):
    with pytest.raises(ValueError):
        from_hex(bad)


def test_to_hex_wants_32_bytes():
    with pytest.raises(ValueError):
        to_hex(b"short")
