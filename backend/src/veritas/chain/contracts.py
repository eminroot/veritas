"""The Veritas contracts as web3 objects: ABIs, deployed addresses and a deployer.

ABIs and bytecode come from `artifacts/`, exported from the Foundry build by
`scripts/export_abis.py`. Addresses come from a `Deployment`, written by the Foundry deploy
script (`contracts/deployments/<chain id>.json`) or by `deploy_system` below, which the
integration tests and the demo use against Anvil.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_utils import to_checksum_address
from web3 import Web3
from web3.contract import Contract

ARTIFACTS = Path(__file__).parent / "artifacts"

SYSTEM = (
    "VeritasHub",
    "VAZN",
    "PassportRegistry",
    "DonationLedger",
    "ReceiptToken",
    "VotingModule",
    "BankPayoutVault",
    "MilestoneEscrow",
    "EscrowFactory",
)
"""Deployed once per chain. MilestoneEscrow here is the implementation every clone copies."""


@cache
def artifact(name: str) -> dict[str, Any]:
    return json.loads((ARTIFACTS / f"{name}.json").read_text(encoding="utf-8"))


def abi(name: str) -> list[dict[str, Any]]:
    return artifact(name)["abi"]


@dataclass(frozen=True)
class Deployment:
    chain_id: int
    start_block: int
    addresses: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Deployment:
        return cls(
            chain_id=int(data["chainId"]),
            start_block=int(data.get("startBlock", 0)),
            addresses={name: to_checksum_address(data[name]) for name in SYSTEM},
        )

    @classmethod
    def load(cls, path: str | Path) -> Deployment:
        return cls.from_json(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_json(self) -> dict[str, Any]:
        return {"chainId": self.chain_id, "startBlock": self.start_block, **self.addresses}

    @property
    def hub(self) -> str:
        return self.addresses["VeritasHub"]


class Contracts:
    """The deployed system on one chain, plus escrow clones by address."""

    def __init__(self, w3: Web3, deployment: Deployment) -> None:
        self.w3 = w3
        self.deployment = deployment

    def get(self, name: str) -> Contract:
        return self.w3.eth.contract(address=self.deployment.addresses[name], abi=abi(name))

    def escrow(self, address: str) -> Contract:
        return self.w3.eth.contract(
            address=to_checksum_address(address), abi=abi("MilestoneEscrow")
        )

    @property
    def hub(self) -> Contract:
        return self.get("VeritasHub")

    @property
    def factory(self) -> Contract:
        return self.get("EscrowFactory")

    @property
    def ledger(self) -> Contract:
        return self.get("DonationLedger")

    @property
    def registry(self) -> Contract:
        return self.get("PassportRegistry")

    @property
    def voting(self) -> Contract:
        return self.get("VotingModule")

    @property
    def vault(self) -> Contract:
        return self.get("BankPayoutVault")

    @property
    def receipts(self) -> Contract:
        return self.get("ReceiptToken")

    @property
    def vazn(self) -> Contract:
        return self.get("VAZN")


def send(w3: Web3, account: LocalAccount, transaction: dict[str, Any]) -> Any:
    """Sign and send one transaction and wait for it. For deploys and tests, not the relayer."""
    transaction = {
        "nonce": w3.eth.get_transaction_count(account.address, "pending"),
        "chainId": w3.eth.chain_id,
        **transaction,
        "from": account.address,
    }
    if "gas" not in transaction:
        transaction["gas"] = int(w3.eth.estimate_gas(transaction) * 1.2) + 50_000
    signed = account.sign_transaction(transaction)
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(signed.raw_transaction)
    )
    if receipt["status"] != 1:
        raise RuntimeError(f"transaction {receipt['transactionHash'].hex()} reverted")
    return receipt


def deploy_system(
    w3: Web3,
    deployer: LocalAccount | bytes,
    *,
    admin: str,
    relayer: str,
    bank: str,
    log: Callable[[str], None] | None = None,
) -> Deployment:
    """Deploy and wire every contract, the same way script/Deploy.s.sol does."""
    if not isinstance(deployer, LocalAccount):
        deployer = Account.from_key(deployer)
    start_block = w3.eth.block_number
    addresses: dict[str, str] = {}

    def deploy(name: str, *args: Any) -> str:
        factory = w3.eth.contract(abi=abi(name), bytecode=artifact(name)["bytecode"])
        receipt = send(
            w3, deployer, factory.constructor(*args).build_transaction({"from": deployer.address})
        )
        addresses[name] = to_checksum_address(receipt["contractAddress"])
        if log:
            log(f"{name} at {addresses[name]}")
        return addresses[name]

    hub = deploy("VeritasHub", admin, relayer, bank)
    for name in ("VAZN", "PassportRegistry", "DonationLedger", "ReceiptToken", "VotingModule"):
        deploy(name, hub)
    deploy("BankPayoutVault", hub)
    implementation = deploy("MilestoneEscrow", hub)
    deploy("EscrowFactory", hub, implementation)
    contract = w3.eth.contract(address=hub, abi=abi("VeritasHub"))
    wiring = contract.functions.wire(
        addresses["VAZN"],
        addresses["DonationLedger"],
        addresses["BankPayoutVault"],
        addresses["VotingModule"],
        addresses["ReceiptToken"],
        addresses["PassportRegistry"],
        addresses["EscrowFactory"],
    )
    send(w3, deployer, wiring.build_transaction({"from": deployer.address}))
    ordered = {name: addresses[name] for name in SYSTEM}
    return Deployment(chain_id=w3.eth.chain_id, start_block=start_block, addresses=ordered)
