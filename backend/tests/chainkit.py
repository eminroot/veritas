"""A local Anvil chain for integration tests, and helpers to drive the relayer and indexer.

Anvil comes with Foundry. Tests that need it are skipped when it is not installed, so the
rest still run anywhere. Set VERITAS_ANVIL to its path if it is not on PATH.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager

from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3

# Anvil's default accounts (mnemonic "test test ... junk"). Never use them anywhere real.
ANVIL_KEYS = [
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
    "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
    "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
    "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
    "0xdbda1821b80551c9d65939329250298aa3472ba22feea921c0cf5d620ea67b97",
    "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",
]

ROLES = ["deployer", "relayer", "bank", "charity", "officer", "donor1", "donor2", "donor3"]
"""Who plays which part. The deployer is also the admin. The example Passport's officer is
account 4, so the officer key signs for it."""


def accounts() -> dict[str, LocalAccount]:
    return {role: Account.from_key(key) for role, key in zip(ROLES, ANVIL_KEYS, strict=False)}


def anvil_binary() -> str | None:
    return os.environ.get("VERITAS_ANVIL") or shutil.which("anvil")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def run_anvil(binary: str) -> Iterator[str]:
    port = _free_port()
    # One slot per epoch makes "finalized" trail "latest" by two blocks, so a test reaches
    # finality by mining a couple of empty blocks.
    process = subprocess.Popen(
        [binary, "--port", str(port), "--chain-id", "31337", "--slots-in-an-epoch", "1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    w3 = Web3(Web3.HTTPProvider(url))
    try:
        for _ in range(100):
            try:
                if w3.is_connected():
                    break
            except Exception:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError("anvil did not start")
        yield url
    finally:
        process.terminate()
        process.wait(timeout=10)


def mine(w3: Web3, blocks: int = 1) -> None:
    w3.provider.make_request("anvil_mine", [hex(blocks)])


def warp(w3: Web3, seconds: int) -> None:
    """Moves the chain's clock forward and mines a block at the new time."""
    w3.provider.make_request("evm_increaseTime", [seconds])
    mine(w3)


def settle(relayer, indexer, w3: Web3, rounds: int = 60) -> None:
    """Runs the relayer and the indexer, mining as it goes, until nothing moves."""
    quiet = 0
    for _ in range(rounds):
        moved = relayer.run_once()
        mine(w3, 1)
        moved = indexer.run_once() > 0 or moved
        quiet = 0 if moved else quiet + 1
        if quiet >= 4:
            return
    raise AssertionError("the relayer and indexer did not settle")
