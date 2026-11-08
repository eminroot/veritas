// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Flows} from "./Flows.t.sol";
import {PythonVectors as V} from "./fixtures/PythonVectors.sol";
import {AllocationHarness} from "./Stop.t.sol";
import {VeritasHub} from "../src/VeritasHub.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";
import {LeafProof, ProjectConfig, VeritasTypes} from "../src/libraries/VeritasTypes.sol";

/// @notice Replays a project's life with every signature, root and proof made by the Python
/// backend (scripts/make_contract_vectors.py). If the two sides disagree on a single byte of
/// a message, a leaf or a config, a call here reverts.
contract PythonSignedTest is Flows {
    MilestoneEscrow internal escrow;

    function setUp() public override {
        vm.warp(V.T0);
        vm.roll(1000);
        // Python signed for a hub at a fixed address, so the hub has to live there.
        deployCodeTo("VeritasHub.sol:VeritasHub", abi.encode(admin, relayer, bank), V.HUB);
        hub = VeritasHub(V.HUB);
        deploySystem();
        vm.prank(admin);
        hub.setOfficer(V.OFFICER, true);
    }

    function test_sameKeysChainAndDomain() public view {
        assertEq(block.chainid, V.CHAIN_ID);
        assertEq(admin, V.ADMIN);
        assertEq(relayer, V.RELAYER);
        assertEq(bank, V.BANK);
        assertEq(charity, V.CHARITY);
        assertEq(hub.domainSeparator(), V.DOMAIN_SEPARATOR);
    }

    function test_aProjectLifeSignedInPython() public {
        ProjectConfig memory config = V.config();
        assertEq(keccak256(abi.encode(config)), V.CONFIG_HASH);
        escrow = MilestoneEscrow(
            factory.createProject(config, V.PASSPORT_HASH, V.PASSPORT_CID, V.LAUNCH_SIGNATURE)
        );
        assertEq(escrow.projectId(), V.PROJECT_ID);

        // An hourly batch the bank signed, with Merkle proofs from the Python tree.
        ledger.anchorBatch(1, V.BATCH_1_ROOT, 3, V.credits1(), V.BATCH_1_SIGNATURE);
        assertEq(vazn.totalSupply(), 470_000);
        bytes32[3] memory leafHashes = [V.LEAF_0_HASH, V.LEAF_1_HASH, V.LEAF_2_HASH];
        for (uint256 i = 0; i < 3; i++) {
            LeafProof memory p = V.leafProof(i);
            assertEq(ledger.verifyLeaf(p.batchId, p.leaf, p.proof), leafHashes[i]);
            receipts.mint(p.batchId, p.leaf, p.proof);
        }
        assertEq(receipts.holderCount(V.PROJECT_ID), 2);

        // Evidence, checks, the officer's decision and the donors' votes.
        vm.warp(V.T0 + 1 hours);
        vm.roll(1001);
        vm.prank(relayer);
        escrow.submitEvidence(0, V.BUNDLE_HASH, V.EVIDENCE_CID, V.EVIDENCE_SIGNATURE);
        vm.prank(relayer);
        escrow.recordChecks(0, 1, V.REPORT_HASH, true);
        escrow.officerDecide(
            MilestoneEscrow.Decision({
                milestone: 0,
                attempt: 1,
                approve: true,
                invoiceHash: V.INVOICE_HASH,
                amount: V.APPROVED_AMOUNT,
                overrideChecks: false,
                reasonHash: bytes32(0)
            }),
            V.DECISION_SIGNATURE
        );
        vm.prank(relayer);
        escrow.openMilestoneVote(0, 2);
        bytes32 ballot = voting.ballotId(address(escrow), VeritasTypes.BALLOT_MILESTONE, 0, 1);
        voting.castVoteBySig(ballot, V.DONOR_1, true, one(V.leafProof(0)), V.VOTE_1_SIGNATURE);
        voting.castVoteBySig(ballot, V.DONOR_2, true, one(V.leafProof(1)), V.VOTE_2_SIGNATURE);
        vm.warp(V.T0 + 73 hours);
        vm.roll(1002);
        voting.close(ballot);
        assertEq(uint8(escrow.milestone(0).status), uint8(MilestoneEscrow.Status.Approved));

        // The bank's daily attestation, the release and the payout.
        vm.warp(V.CUTOFF_TIME);
        vm.roll(1003);
        ledger.attestBalance(
            1, V.CUTOFF_BLOCK, V.CUTOFF_TIME, 470_000, V.STATEMENT_HASH, V.BALANCE_SIGNATURE
        );
        escrow.release(0);
        assertEq(vault.instruction(1).invoiceHash, V.INVOICE_HASH);
        vault.confirm(1, V.PAYOUT_REF, V.PAYOUT_SIGNATURE);
        assertEq(uint8(escrow.milestone(0).status), uint8(MilestoneEscrow.Status.Paid));
        assertEq(vazn.totalSupply(), 70_000);

        // A stop proposal and an amendment, both signed in Python, wait for votes.
        escrow.proposeStop(V.STOP_REASON, V.STOP_SIGNATURE);
        assertTrue(escrow.stopVotePending());
        registry.proposeAmendment(
            V.PROJECT_ID,
            2,
            V.AMENDMENT_PASSPORT_HASH,
            V.AMENDMENT_CID,
            V.AMENDMENT_CONTRACTOR_HASH,
            V.AMENDMENT_SIGNATURE
        );
        assertEq(registry.pendingAmendment(V.PROJECT_ID).version, 2);

        // A provider-mode batch that the bank settles a day later.
        vm.prank(relayer);
        ledger.anchorBatch(2, V.BATCH_2_ROOT, 1, V.credits2(), "");
        ledger.settleBatch(2, V.credits2(), V.SETTLEMENT_SIGNATURE);
        LeafProof memory late = V.leafProof(3);
        assertEq(ledger.verifyLeaf(late.batchId, late.leaf, late.proof), V.LEAF_3_HASH);

        // Donor 1 moves to a new phone; donor 2 refuses a rotation they did not ask for.
        uint256 receipt1 = receipts.receiptId(V.PROJECT_ID, V.DONOR_1);
        receipts.rotateBySig(receipt1, V.DONOR_1_NEW, V.ROTATION_DEADLINE, V.ROTATION_SIGNATURE);
        assertEq(receipts.controllerOf(V.PROJECT_ID, V.DONOR_1), V.DONOR_1_NEW);
        uint256 receipt2 = receipts.receiptId(V.PROJECT_ID, V.DONOR_2);
        vm.prank(relayer);
        receipts.requestRotation(receipt2, V.DONOR_2_THIEF);
        receipts.cancelRotation(receipt2, V.CANCEL_SIGNATURE);

        // The charity withdraws and both donors take refunds of what is left.
        escrow.withdraw(V.WITHDRAW_REASON, V.WITHDRAW_SIGNATURE);
        LeafProof[] memory donor1 = new LeafProof[](2);
        donor1[0] = V.leafProof(0);
        donor1[1] = V.leafProof(2);
        escrow.claim(
            V.DONOR_1,
            VeritasTypes.CHOICE_REFUND,
            address(0),
            V.CHOICE_DEADLINE,
            donor1,
            V.CHOICE_1_SIGNATURE
        );
        assertEq(vault.instruction(2).amount, V.REFUND_1_AMOUNT);
        vault.confirm(2, V.REFUND_REF, V.REFUND_SIGNATURE);

        LeafProof[] memory donor2 = new LeafProof[](2);
        donor2[0] = V.leafProof(1);
        donor2[1] = V.leafProof(3);
        escrow.claim(
            V.DONOR_2,
            VeritasTypes.CHOICE_REFUND,
            address(0),
            V.CHOICE_DEADLINE,
            donor2,
            V.CHOICE_2_SIGNATURE
        );
        assertEq(vault.instruction(3).amount, V.REFUND_2_AMOUNT);
        vault.fail(3, V.FAILURE_REASON, V.FAILURE_SIGNATURE);
        assertEq(escrow.retryBalance(V.DONOR_2), V.REFUND_2_AMOUNT);

        // Every vAZN left is in the escrow: the refund that failed plus one qəpik of rounding.
        assertEq(vazn.totalSupply(), vazn.balanceOf(address(escrow)));
        assertEq(vazn.totalSupply(), V.REFUND_2_AMOUNT + 1);

        bytes32 completion = keccak256(
            abi.encode(
                VeritasTypes.COMPLETION_TYPEHASH,
                V.PROJECT_ID,
                V.COMPLETION_REPORT,
                keccak256(bytes("bafy-done"))
            )
        );
        assertEq(hub.hashTypedData(completion), V.COMPLETION_DIGEST);
    }

    function test_allocationMatchesPython() public {
        AllocationHarness harness = new AllocationHarness();
        for (uint256 i = 0; i < V.ALLOCATION_CASES; i++) {
            (uint64 amount, uint64[] memory remaining, uint8 rule, uint64[] memory parts) =
                V.allocationCase(i);
            uint64[] memory got = harness.allocate(amount, remaining, rule);
            assertEq(got.length, parts.length);
            for (uint256 j = 0; j < parts.length; j++) {
                assertEq(got[j], parts[j]);
            }
        }
    }
}
