"""Sign a whole project lifecycle in Python and write it out for the Foundry tests.

    uv run python scripts/make_contract_vectors.py

writes `contracts/test/fixtures/PythonVectors.sol`. `contracts/test/PythonSigned.t.sol` replays
it against the real contracts: launch, an hourly batch, evidence, checks, the officer's
decision, two donor votes, the bank's attestation, release and payout, then a key rotation,
a provider-mode settlement, a stop and the refunds. Every signature and Merkle proof in it was
made here, so the test proves the Python side and the contracts agree on every byte.
`tests/test_contract_vectors.py` fails when the file on disk is out of date.
"""

from __future__ import annotations

import random
import sys
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

from eth_abi import encode
from eth_keys import keys

from veritas.chain import eip712
from veritas.chain.leaves import DonationLeaf, donation_tree
from veritas.chain.project import Credit, ProjectConfig, credits_hash
from veritas.core.hashing import keccak256, sha256
from veritas.domain.allocation import AllocationRule, allocate
from veritas.passport import Passport

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "examples" / "passport.example.json"
OUTPUT = ROOT / "contracts" / "test" / "fixtures" / "PythonVectors.sol"

CHAIN_ID = 31337
HUB = "0x000000000000000000000000000000000000bEEF"
T0 = 1_800_000_000
HOUR = 3600

# Same keys as Base.t.sol for the system roles; anvil's well-known keys for the people.
KEYS = {
    "ADMIN": 0xA11CE,
    "RELAYER": 0x5E1A7,
    "BANK": 0xBA4C,
    "CHARITY": 0xC4A1,
    "OFFICER": 0x47E179EC197488593B187F80A00EB0DA91F1B9D0B13F8733639F19C30A34926A,
    "DONOR_1": 0x59C6995E998F97A5A0044966F0945389DC9E86DAE88C7A8412F4603B6B78690D,
    "DONOR_2": 0x5DE4111AFA1A4B94908F83103EB1F1706367C2E68CA870FC3FB9A804CDAB365A,
    "DONOR_1_NEW": 0x7C852118294E51E653712A81E05800F419141751BE58F605C371E15141B007A6,
    "DONOR_2_THIEF": 0x8B3A350CF5C34C9194CA85829A2DF0EC3153BE0318B5E2D3348E872092EDFFBA,
}


def key_bytes(name: str) -> bytes:
    return KEYS[name].to_bytes(32, "big")


def address(name: str) -> str:
    return keys.PrivateKey(key_bytes(name)).public_key.to_checksum_address()


DOMAIN = eip712.Domain(CHAIN_ID, HUB)


def signed(name: str, primary: str, message: dict) -> bytes:
    return eip712.sign(key_bytes(name), DOMAIN, primary, message)


def h(text: str) -> bytes:
    return sha256(text.encode())


# ---------------------------------------------------------------- Solidity literals


def b32(value: bytes) -> str:
    assert len(value) == 32
    return "0x" + value.hex()


def b16(value: bytes) -> str:
    assert len(value) == 16
    return f"bytes16(0x{value.hex()})"


def hexbytes(value: bytes) -> str:
    return f'hex"{value.hex()}"'


def uint_array(target: str, values: Iterable[int], kind: str = "uint64") -> list[str]:
    """Lines that fill an array. `target` is a name or a declaration like "uint64[] memory x"."""
    values = list(values)
    name = target.split()[-1]
    lines = [f"{target} = new {kind}[]({len(values)});"]
    lines += [f"{name}[{i}] = {v};" for i, v in enumerate(values)]
    return lines


class Writer:
    def __init__(self) -> None:
        self.constants: list[str] = []
        self.functions: list[str] = []

    def const(self, kind: str, name: str, value: str) -> None:
        self.constants.append(f"    {kind} internal constant {name} = {value};")

    def function(self, signature: str, body: list[str]) -> None:
        lines = [f"    function {signature} {{"]
        lines += [f"        {line}" for line in body]
        lines.append("    }")
        self.functions.append("\n".join(lines))


def leaf_lines(var: str, leaf: DonationLeaf) -> list[str]:
    return [
        f"{var} = DonationLeaf({{",
        f"    donationId: {b16(leaf.donation_id.bytes)},",
        f"    holder: {leaf.holder},",
        f"    projectId: {b16(leaf.project_id.bytes)},",
        f"    milestone: {leaf.milestone},",
        f"    amount: {leaf.amount},",
        f"    trigger: {b32(leaf.trigger)},",
        f"    salt: {b32(leaf.salt)}",
        "});",
    ]


# ---------------------------------------------------------------- the scenario


def build() -> str:
    w = Writer()
    passport = Passport.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))
    pid = passport.project_id
    config = ProjectConfig.from_passport(passport, address("CHARITY"))

    w.const("uint256", "CHAIN_ID", str(CHAIN_ID))
    w.const("address", "HUB", DOMAIN.verifying_contract)
    w.const("uint256", "T0", str(T0))
    for name in KEYS:
        w.const("address", name, address(name))
    w.const("bytes32", "DOMAIN_SEPARATOR", b32(DOMAIN.separator()))
    w.const("bytes16", "PROJECT_ID", b16(pid.bytes))

    # Launch: the charity signs the Passport hash and the config derived from it.
    passport_hash = passport.digest()
    cid = "bafkreie5example0passport0cid0for0the0vector0tests0only"
    launch = {
        "projectId": pid.bytes,
        "version": 1,
        "passportHash": passport_hash,
        "cid": cid,
        "configHash": config.hash(),
    }
    w.const("bytes32", "PASSPORT_HASH", b32(passport_hash))
    w.const("string", "PASSPORT_CID", f'"{cid}"')
    w.const("bytes32", "CONFIG_HASH", b32(config.hash()))
    w.const("bytes", "LAUNCH_SIGNATURE", hexbytes(signed("CHARITY", "ProjectLaunch", launch)))
    rules, stop = config.rules, config.stop
    w.function(
        "config() internal pure returns (ProjectConfig memory c)",
        [
            *uint_array("uint64[] memory budgets", config.budgets),
            *uint_array("uint64[] memory deadlines", config.evidence_deadlines),
            "c = ProjectConfig({",
            f"    projectId: {b16(pid.bytes)},",
            f"    charity: {config.charity},",
            f"    officer: {config.officer},",
            f"    category: {config.category},",
            f"    allocation: {config.allocation},",
            "    budgets: budgets,",
            "    evidenceDeadlines: deadlines,",
            "    rules: DecisionRules({",
            f"        voteWindow: {rules.vote_window},",
            f"        turnoutExtension: {rules.turnout_extension},",
            f"        minTurnoutBps: {rules.min_turnout_bps},",
            f"        approvalBps: {rules.approval_bps},",
            f"        minVoteAmount: {rules.min_vote_amount},",
            f"        fallbackApproves: {str(rules.fallback_approves).lower()}",
            "    }),",
            "    stop: StopRules({",
            f"        evidenceGrace: {stop.evidence_grace},",
            f"        choiceWindow: {stop.choice_window},",
            f"        unclaimedRedirects: {str(stop.unclaimed_redirects).lower()}",
            "    }),",
            f"    contractorHash: {b32(config.contractor_hash)}",
            "});",
        ],
    )

    # Batch 1, bank mode: milestone 0 fully funded by two donors, and some for milestone 1.
    def leaf(n: int, holder: str, milestone: int, amount: int) -> DonationLeaf:
        return DonationLeaf(
            donation_id=UUID(int=0xD0000 + n),
            holder=address(holder),
            project_id=pid,
            milestone=milestone,
            amount=amount,
            salt=h(f"salt {n}"),
        )

    batch1 = [
        leaf(1, "DONOR_1", 0, 300_000),
        leaf(2, "DONOR_2", 0, 120_000),
        leaf(3, "DONOR_1", 1, 50_000),
    ]
    tree1 = donation_tree(batch1)
    credits1 = [Credit(pid, (420_000, 50_000, 0))]
    attestation = {
        "batchId": 1,
        "root": tree1.root,
        "leafCount": len(batch1),
        "total": 470_000,
        "creditsHash": credits_hash(credits1),
    }
    w.const("bytes32", "BATCH_1_ROOT", b32(tree1.root))
    w.const("bytes", "BATCH_1_SIGNATURE", hexbytes(signed("BANK", "BatchAttestation", attestation)))

    batch2 = [leaf(4, "DONOR_2", 2, 2_000)]
    tree2 = donation_tree(batch2)
    credits2 = [Credit(pid, (0, 0, 2_000))]
    settlement = {"batchId": 2, "creditsHash": credits_hash(credits2)}
    w.const("bytes32", "BATCH_2_ROOT", b32(tree2.root))
    w.const("bytes", "SETTLEMENT_SIGNATURE", hexbytes(signed("BANK", "Settlement", settlement)))

    for number, credits in ((1, credits1), (2, credits2)):
        body = [f"credits = new Credit[]({len(credits)});"]
        for i, credit in enumerate(credits):
            body += uint_array(f"uint64[] memory amounts{i}", credit.amounts)
            body.append(f"credits[{i}] = Credit({b16(credit.project_id.bytes)}, amounts{i});")
        w.function(f"credits{number}() internal pure returns (Credit[] memory credits)", body)

    proofs = [(1, tree1, i, batch1[i]) for i in range(3)] + [(2, tree2, 0, batch2[0])]
    body = ["DonationLeaf memory leaf;", "bytes32[] memory proof;"]
    for number, (batch_id, tree, index, item) in enumerate(proofs):
        path = tree.proof(index)
        body.append(f"if (i == {number}) {{")
        body += [f"    {line}" for line in leaf_lines("leaf", item)]
        body.append(f"    proof = new bytes32[]({len(path)});")
        body += [f"    proof[{k}] = {b32(node)};" for k, node in enumerate(path)]
        body.append(f"    return LeafProof({batch_id}, leaf, proof);")
        body.append("}")
    body.append('revert("no such leaf");')
    w.function("leafProof(uint256 i) internal pure returns (LeafProof memory)", body)
    hashes = {number: item.hash() for number, (_, _, _, item) in enumerate(proofs)}
    for number, digest in hashes.items():
        w.const("bytes32", f"LEAF_{number}_HASH", b32(digest))

    # Evidence, checks and the officer's decision for milestone 0, attempt 1.
    bundle = h("evidence bundle, milestone 0, attempt 1")
    report = h("check report, milestone 0, attempt 1")
    invoice = h("invoice DT-2027-014 from Dag Tikinti MMC")
    approved = 400_000
    evidence = {"projectId": pid.bytes, "milestone": 0, "attempt": 1, "bundleHash": bundle}
    decision = {
        "projectId": pid.bytes,
        "milestone": 0,
        "attempt": 1,
        "approve": True,
        "bundleHash": bundle,
        "reportHash": report,
        "invoiceHash": invoice,
        "amount": approved,
        "overrideChecks": False,
        "reasonHash": bytes(32),
    }
    w.const("bytes32", "BUNDLE_HASH", b32(bundle))
    w.const("string", "EVIDENCE_CID", '"bafkreie5example0evidence0cid"')
    w.const("bytes", "EVIDENCE_SIGNATURE", hexbytes(signed("CHARITY", "Evidence", evidence)))
    w.const("bytes32", "REPORT_HASH", b32(report))
    w.const("bytes32", "INVOICE_HASH", b32(invoice))
    w.const("uint64", "APPROVED_AMOUNT", str(approved))
    w.const("bytes", "DECISION_SIGNATURE", hexbytes(signed("OFFICER", "Decision", decision)))

    for n in (1, 2):
        vote = {
            "projectId": pid.bytes,
            "holder": address(f"DONOR_{n}"),
            "kind": eip712.BALLOT_MILESTONE,
            "milestone": 0,
            "round": 1,
            "approve": True,
        }
        w.const("bytes", f"VOTE_{n}_SIGNATURE", hexbytes(signed(f"DONOR_{n}", "Vote", vote)))

    # The bank's daily attestation once the vote has closed, then the payout confirmation.
    cutoff_block, cutoff_time = 1002, T0 + 74 * HOUR
    balance = {
        "day": 1,
        "cutoffBlock": cutoff_block,
        "cutoffTime": cutoff_time,
        "balance": 470_000,
        "statementHash": h("statement 2027-01-18"),
    }
    w.const("uint64", "CUTOFF_BLOCK", str(cutoff_block))
    w.const("uint64", "CUTOFF_TIME", str(cutoff_time))
    w.const("bytes32", "STATEMENT_HASH", b32(balance["statementHash"]))
    w.const("bytes", "BALANCE_SIGNATURE", hexbytes(signed("BANK", "BalanceAttestation", balance)))
    payout_ref = h("KAPITAL-PAY-000001")
    payout = {"instructionId": 1, "amount": approved, "paymentRef": payout_ref}
    w.const("bytes32", "PAYOUT_REF", b32(payout_ref))
    w.const("bytes", "PAYOUT_SIGNATURE", hexbytes(signed("BANK", "PayoutConfirmation", payout)))

    # A stop is proposed and an amendment too, before the charity withdraws instead.
    stop_reason = h("contractor stopped answering")
    stop_proposal = {"projectId": pid.bytes, "round": 1, "reasonHash": stop_reason}
    w.const("bytes32", "STOP_REASON", b32(stop_reason))
    w.const("bytes", "STOP_SIGNATURE", hexbytes(signed("OFFICER", "StopProposal", stop_proposal)))
    amendment = {
        "projectId": pid.bytes,
        "version": 2,
        "passportHash": h("passport version 2"),
        "cid": "bafkreie5example0passport0v2",
        "contractorHash": h("another contractor"),
    }
    w.const("bytes32", "AMENDMENT_PASSPORT_HASH", b32(amendment["passportHash"]))
    w.const("string", "AMENDMENT_CID", f'"{amendment["cid"]}"')
    w.const("bytes32", "AMENDMENT_CONTRACTOR_HASH", b32(amendment["contractorHash"]))
    w.const("bytes", "AMENDMENT_SIGNATURE", hexbytes(signed("CHARITY", "Amendment", amendment)))

    # Donor 1 moves their receipt to a new phone; someone tries to take donor 2's.
    receipt_1 = int.from_bytes(receipt_id(pid, address("DONOR_1")), "big")
    receipt_2 = int.from_bytes(receipt_id(pid, address("DONOR_2")), "big")
    rotation = {
        "receiptId": receipt_1,
        "newKey": address("DONOR_1_NEW"),
        "nonce": 0,
        "deadline": T0 + 100 * HOUR,
    }
    # The thief's request is made at the bank's cut-off time and waits 48 hours.
    cancel = {
        "receiptId": receipt_2,
        "newKey": address("DONOR_2_THIEF"),
        "readyAt": cutoff_time + 48 * HOUR,
    }
    w.const("uint64", "ROTATION_DEADLINE", str(rotation["deadline"]))
    w.const("bytes", "ROTATION_SIGNATURE", hexbytes(signed("DONOR_1", "KeyRotation", rotation)))
    w.const("bytes", "CANCEL_SIGNATURE", hexbytes(signed("DONOR_2", "RotationCancel", cancel)))

    withdraw_reason = h("the school was rebuilt by the state")
    withdraw = {"projectId": pid.bytes, "reasonHash": withdraw_reason}
    w.const("bytes32", "WITHDRAW_REASON", b32(withdraw_reason))
    w.const("bytes", "WITHDRAW_SIGNATURE", hexbytes(signed("CHARITY", "Withdraw", withdraw)))

    # Refunds: each leaf is worth its share of what its milestone still holds.
    funded = {0: 420_000, 1: 50_000, 2: 2_000}
    released = {0: approved, 1: 0, 2: 0}

    def share(item: DonationLeaf) -> int:
        m = item.milestone
        return item.amount * (funded[m] - released[m]) // funded[m]

    refund_1 = share(batch1[0]) + share(batch1[2])
    refund_2 = share(batch1[1]) + share(batch2[0])
    deadline = T0 + 200 * HOUR
    for n, signer, amount in ((1, "DONOR_1_NEW", refund_1), (2, "DONOR_2", refund_2)):
        choice = {
            "projectId": pid.bytes,
            "holder": address(f"DONOR_{n}"),
            "action": eip712.CHOICE_REFUND,
            "target": "0x0000000000000000000000000000000000000000",
            "nonce": 0,
            "deadline": deadline,
        }
        w.const("uint64", f"REFUND_{n}_AMOUNT", str(amount))
        w.const("bytes", f"CHOICE_{n}_SIGNATURE", hexbytes(signed(signer, "Choice", choice)))
    w.const("uint64", "CHOICE_DEADLINE", str(deadline))
    refund_ref = h("KAPITAL-REFUND-000002")
    confirmation = {"instructionId": 2, "amount": refund_1, "paymentRef": refund_ref}
    w.const("bytes32", "REFUND_REF", b32(refund_ref))
    w.const(
        "bytes",
        "REFUND_SIGNATURE",
        hexbytes(signed("BANK", "PayoutConfirmation", confirmation)),
    )
    failure_reason = h("card expired")
    failure = {"instructionId": 3, "reasonHash": failure_reason}
    w.const("bytes32", "FAILURE_REASON", b32(failure_reason))
    w.const("bytes", "FAILURE_SIGNATURE", hexbytes(signed("BANK", "PayoutFailure", failure)))

    # Completion cannot happen in this story, so only its digest is checked.
    completion = {"projectId": pid.bytes, "reportHash": h("completion"), "cid": "bafy-done"}
    w.const("bytes32", "COMPLETION_REPORT", b32(completion["reportHash"]))
    w.const("bytes32", "COMPLETION_DIGEST", b32(eip712.digest(DOMAIN, "Completion", completion)))

    # Allocation: the Python rule on random inputs, for the Solidity port.
    rng = random.Random(8785)
    cases = []
    for _ in range(40):
        remaining = [rng.choice([0, rng.randint(1, 10**9)]) for _ in range(rng.randint(1, 8))]
        if sum(remaining) == 0:
            remaining[0] = 1
        rule = rng.choice(list(AllocationRule))
        amount = rng.randint(1, sum(remaining))
        cases.append((amount, remaining, rule, allocate(amount, remaining, rule)))
    w.const("uint256", "ALLOCATION_CASES", str(len(cases)))
    body = []
    for i, (amount, remaining, rule, parts) in enumerate(cases):
        code = 0 if rule is AllocationRule.PRO_RATA else 1
        body.append(f"if (i == {i}) {{")
        body.append(f"    amount = {amount};")
        body.append(f"    rule = {code};")
        body += [f"    {line}" for line in uint_array("remaining", remaining)]
        body += [f"    {line}" for line in uint_array("parts", parts)]
        body.append("    return (amount, remaining, rule, parts);")
        body.append("}")
    body.append('revert("no such case");')
    w.function(
        "allocationCase(uint256 i) internal pure returns "
        "(uint64 amount, uint64[] memory remaining, uint8 rule, uint64[] memory parts)",
        body,
    )

    header = [
        "// SPDX-License-Identifier: UNLICENSED",
        "// Generated by backend/scripts/make_contract_vectors.py from the Python implementation.",
        "// Do not edit. Run `uv run python scripts/make_contract_vectors.py` in backend/ instead.",
        "pragma solidity ^0.8.28;",
        "",
        "import {",
        "    Credit,",
        "    DecisionRules,",
        "    DonationLeaf,",
        "    LeafProof,",
        "    ProjectConfig,",
        "    StopRules",
        '} from "../../src/libraries/VeritasTypes.sol";',
        "",
        "library PythonVectors {",
    ]
    return "\n".join([*header, *w.constants, "", "\n\n".join(w.functions), "}", ""])


def receipt_id(project_id: UUID, holder: str) -> bytes:
    return keccak256(encode(["bytes16", "address"], [project_id.bytes, holder]))


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build(), encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
