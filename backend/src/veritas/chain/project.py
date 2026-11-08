"""A project's on-chain config, derived from its Passport.

The escrow cannot read JSON, so at launch the factory receives the parts of the Passport it
enforces: milestone amounts, evidence deadlines, voting and stop rules, the officer, and the
contractor as a hash. The charity signs the hash of exactly these values next to the Passport
hash, which binds the rules on-chain to the document donors read. The field order and types
match `ProjectConfig` in VeritasTypes.sol.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from eth_abi import encode
from eth_utils import to_checksum_address

from veritas.core.hashing import keccak256
from veritas.core.identifiers import normalize_voen
from veritas.domain.allocation import AllocationRule
from veritas.passport.models import Category, Passport

CATEGORY_CODES: dict[Category, int] = {category: code for code, category in enumerate(Category)}
ALLOCATION_CODES = {AllocationRule.PRO_RATA: 0, AllocationRule.SEQUENTIAL: 1}

DECISION_RULES_TYPE = "(uint32,uint32,uint16,uint16,uint64,bool)"
STOP_RULES_TYPE = "(uint32,uint32,bool)"
PROJECT_CONFIG_TYPE = (
    f"(bytes16,address,address,uint8,uint8,uint64[],uint64[],{DECISION_RULES_TYPE},"
    f"{STOP_RULES_TYPE},bytes32)"
)
CREDITS_TYPE = "(bytes16,uint64[])[]"

HOUR = 3600
DAY = 24 * HOUR


def contractor_hash(voen: str) -> bytes:
    """How the chain names a contractor: a hash of their VÖEN, the key the bank pays against.

    A company's VÖEN is public, so this hides nothing. It keeps payment details off-chain
    while still letting the escrow refuse a release to anyone but the Passport's contractor.
    """
    return keccak256(b"veritas:contractor:" + normalize_voen(voen).encode())


@dataclass(frozen=True)
class DecisionRules:
    vote_window: int
    turnout_extension: int
    min_turnout_bps: int
    approval_bps: int
    min_vote_amount: int
    fallback_approves: bool

    def abi_value(self) -> tuple[Any, ...]:
        return (
            self.vote_window,
            self.turnout_extension,
            self.min_turnout_bps,
            self.approval_bps,
            self.min_vote_amount,
            self.fallback_approves,
        )


@dataclass(frozen=True)
class StopRules:
    evidence_grace: int
    choice_window: int
    unclaimed_redirects: bool

    def abi_value(self) -> tuple[Any, ...]:
        return (self.evidence_grace, self.choice_window, self.unclaimed_redirects)


@dataclass(frozen=True)
class ProjectConfig:
    project_id: UUID
    charity: str
    officer: str
    category: int
    allocation: int
    budgets: tuple[int, ...]
    evidence_deadlines: tuple[int, ...]
    rules: DecisionRules
    stop: StopRules
    contractor_hash: bytes

    @classmethod
    def from_passport(cls, passport: Passport, charity_signer: str) -> ProjectConfig:
        """`charity_signer` is the charity's registered on-chain key, which the Passport
        does not carry because it can change between projects."""
        decision, stop = passport.decision, passport.stop
        return cls(
            project_id=passport.project_id,
            charity=to_checksum_address(charity_signer),
            officer=passport.officer.address,
            category=CATEGORY_CODES[passport.category],
            allocation=ALLOCATION_CODES[passport.allocation],
            budgets=tuple(passport.milestone_amounts()),
            evidence_deadlines=tuple(
                int(passport.evidence_deadline(i).timestamp())
                for i in range(len(passport.milestones))
            ),
            rules=DecisionRules(
                vote_window=decision.vote_window_hours * HOUR,
                turnout_extension=decision.turnout_extension_hours * HOUR,
                min_turnout_bps=decision.min_turnout_bps,
                approval_bps=decision.approval_bps,
                min_vote_amount=decision.min_vote_qapik,
                fallback_approves=decision.low_turnout_fallback == "officer_decision",
            ),
            stop=StopRules(
                evidence_grace=stop.evidence_grace_days * DAY,
                choice_window=stop.choice_window_days * DAY,
                unclaimed_redirects=stop.unclaimed == "redirect_same_category",
            ),
            contractor_hash=contractor_hash(passport.contractor.voen),
        )

    def abi_value(self) -> tuple[Any, ...]:
        """The tuple web3 and eth_abi take for the Solidity struct."""
        return (
            self.project_id.bytes,
            self.charity,
            self.officer,
            self.category,
            self.allocation,
            list(self.budgets),
            list(self.evidence_deadlines),
            self.rules.abi_value(),
            self.stop.abi_value(),
            self.contractor_hash,
        )

    def hash(self) -> bytes:
        """keccak256(abi.encode(config)), as VeritasTypes.hashConfig computes it."""
        return keccak256(encode([PROJECT_CONFIG_TYPE], [self.abi_value()]))


def launch_message(
    passport: Passport, config: ProjectConfig, passport_hash: bytes, cid: str
) -> dict[str, Any]:
    """The ProjectLaunch message the charity signs to put a Passport on-chain."""
    if config.project_id != passport.project_id:
        raise ValueError("the config belongs to another project")
    if passport.version != 1:
        raise ValueError("a project launches with version 1, later versions are amendments")
    return {
        "projectId": passport.project_id.bytes,
        "version": passport.version,
        "passportHash": passport_hash,
        "cid": cid,
        "configHash": config.hash(),
    }


@dataclass(frozen=True)
class Credit:
    """One project's share of an hourly batch: qəpik per milestone."""

    project_id: UUID
    amounts: tuple[int, ...]

    def abi_value(self) -> tuple[Any, ...]:
        return (self.project_id.bytes, list(self.amounts))


def credits_hash(credits: Sequence[Credit]) -> bytes:
    """keccak256(abi.encode(credits)), as VeritasTypes.hashCredits computes it."""
    return keccak256(encode([CREDITS_TYPE], [[credit.abi_value() for credit in credits]]))
