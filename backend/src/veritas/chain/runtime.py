"""The chain as the running services see it: one connection, one deployment, one domain."""

from __future__ import annotations

from dataclasses import dataclass

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from veritas.chain import eip712
from veritas.chain.contracts import Contracts, Deployment


@dataclass(frozen=True)
class Chain:
    contracts: Contracts
    domain: eip712.Domain

    @property
    def w3(self) -> Web3:
        return self.contracts.w3

    @property
    def deployment(self) -> Deployment:
        return self.contracts.deployment

    @classmethod
    def connect(cls, rpc_url: str, deployment: Deployment) -> Chain:
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        # Polygon's blocks carry more extra data than Ethereum's; web3 needs telling.
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        # No call of ours follows an EIP-3668 OffchainLookup: a contract could name any URL.
        w3.provider.global_ccip_read_enabled = False
        return cls.of(Contracts(w3, deployment))

    @classmethod
    def of(cls, contracts: Contracts) -> Chain:
        domain = eip712.Domain(contracts.deployment.chain_id, contracts.deployment.hub)
        return cls(contracts=contracts, domain=domain)
