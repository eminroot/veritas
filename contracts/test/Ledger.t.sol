// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Flows} from "./Flows.t.sol";
import {DonationLedger} from "../src/DonationLedger.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";
import {ReceiptToken} from "../src/ReceiptToken.sol";
import {Signatures} from "../src/libraries/Signatures.sol";
import {Credit, DonationLeaf, LeafProof, VeritasTypes} from "../src/libraries/VeritasTypes.sol";

contract LedgerTest is Flows {
    MilestoneEscrow internal escrow;
    bytes16 internal pid;

    function setUp() public override {
        super.setUp();
        escrow = launchDefault(1);
        pid = escrow.projectId();
    }

    function test_bankSignedBatchCreditsAndMints() public {
        DonationLeaf[] memory leaves =
            leaves2(makeLeaf(pid, donor(1), 0, 30_000), makeLeaf(pid, donor(2), 1, 70_000));
        LeafProof[] memory proofs = anchor(leaves);
        assertEq(ledger.lastBatchId(), 1);
        assertEq(vazn.balanceOf(address(escrow)), 100_000);
        assertEq(escrow.milestone(0).funded, 30_000);
        assertEq(escrow.milestone(1).funded, 70_000);
        (,, uint64 total, uint32 leafCount, bool settled) = ledger.batches(1);
        assertEq(total, 100_000);
        assertEq(leafCount, 2);
        assertTrue(settled);
        assertEq(ledger.verifyLeaf(1, proofs[0].leaf, proofs[0].proof), hashLeaf(leaves[0]));
        assertTrue(ledger.isInBatch(1, proofs[1].leaf, proofs[1].proof));
    }

    function test_batchesAreNumberedInOrder() public {
        DonationLeaf[] memory leaves = leaves1(makeLeaf(pid, donor(1), 0, 1000));
        (bytes32 root,) = merkle(leaves);
        Credit[] memory credits = creditsFor(leaves);
        bytes memory signature = bankBatchSignature(2, root, 1, credits);
        vm.expectRevert(abi.encodeWithSelector(DonationLedger.WrongBatchId.selector, 1, 2));
        ledger.anchorBatch(2, root, 1, credits, signature);
    }

    function test_bankSignatureCoversRootAndCredits() public {
        DonationLeaf[] memory leaves = leaves1(makeLeaf(pid, donor(1), 0, 1000));
        (bytes32 root,) = merkle(leaves);
        Credit[] memory credits = creditsFor(leaves);
        bytes memory signature = bankBatchSignature(1, root, 1, credits);
        credits[0].amounts[0] = 2000; // inflate the credit after the bank signed
        vm.expectRevert(abi.encodeWithSelector(Signatures.BadSignature.selector, bank));
        ledger.anchorBatch(1, root, 1, credits, signature);
    }

    function test_creditsCannotExceedABudget() public {
        DonationLeaf[] memory leaves = leaves1(makeLeaf(pid, donor(1), 0, 420_001));
        (bytes32 root,) = merkle(leaves);
        Credit[] memory credits = creditsFor(leaves);
        bytes memory signature = bankBatchSignature(1, root, 1, credits);
        vm.expectRevert(abi.encodeWithSelector(MilestoneEscrow.OverBudget.selector, 0));
        ledger.anchorBatch(1, root, 1, credits, signature);
    }

    function test_unknownProjectIsRefused() public {
        bytes16 stranger = projectIdOf(99);
        DonationLeaf[] memory leaves = leaves1(makeLeaf(stranger, donor(1), 0, 1000));
        (bytes32 root,) = merkle(leaves);
        Credit[] memory credits = creditsFor(leaves);
        bytes memory signature = bankBatchSignature(1, root, 1, credits);
        vm.expectRevert(abi.encodeWithSelector(DonationLedger.UnknownProject.selector, stranger));
        ledger.anchorBatch(1, root, 1, credits, signature);
    }

    function test_providerModeMintsOnlyWhenTheBankSettles() public {
        DonationLeaf[] memory leaves = leaves1(makeLeaf(pid, donor(1), 0, 5000));
        (bytes32 root, bytes32[][] memory paths) = merkle(leaves);
        Credit[] memory credits = creditsFor(leaves);

        vm.expectRevert(DonationLedger.NotRelayer.selector);
        ledger.anchorBatch(1, root, 1, credits, "");

        vm.prank(relayer);
        ledger.anchorBatch(1, root, 1, credits, "");
        assertEq(escrow.milestone(0).funded, 5000);
        assertEq(vazn.balanceOf(address(escrow)), 0);
        vm.expectRevert(abi.encodeWithSelector(DonationLedger.BatchNotSettled.selector, 1));
        ledger.verifyLeaf(1, leaves[0], paths[0]);
        assertTrue(ledger.isInBatch(1, leaves[0], paths[0]));

        bytes32 creditsHash = keccak256(abi.encode(credits));
        bytes memory signature = sign(
            BANK_PK, keccak256(abi.encode(VeritasTypes.SETTLEMENT_TYPEHASH, uint64(1), creditsHash))
        );
        credits[0].amounts[0] = 6000;
        vm.expectRevert(DonationLedger.CreditsMismatch.selector);
        ledger.settleBatch(1, credits, signature);
        credits[0].amounts[0] = 5000;
        ledger.settleBatch(1, credits, signature);
        assertEq(vazn.balanceOf(address(escrow)), 5000);
        ledger.verifyLeaf(1, leaves[0], paths[0]);
        vm.expectRevert(abi.encodeWithSelector(DonationLedger.AlreadySettled.selector, 1));
        ledger.settleBatch(1, credits, signature);
    }

    function test_badProofIsRefused() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 1000));
        p.leaf.amount = 1001;
        vm.expectRevert(DonationLedger.BadProof.selector);
        ledger.verifyLeaf(p.batchId, p.leaf, p.proof);
    }

    function test_balancedAttestationAllowsReleases() public {
        anchorOne(makeLeaf(pid, donor(1), 0, 1000));
        attestBalanced();
        assertTrue(ledger.reconciled());
        assertTrue(ledger.lastBalanced());
    }

    function test_mismatchFreezesReleasesUntilBalancedAgain() public {
        anchorOne(makeLeaf(pid, donor(1), 0, 1000));
        attestBalanced();
        attestWith(1, true); // the bank holds one qəpik less than the supply
        assertFalse(ledger.reconciled());
        assertFalse(hub.releasesAllowed());
        attestBalanced();
        assertTrue(hub.releasesAllowed());
    }

    function test_attestationsMoveForward() public {
        attestBalanced();
        vm.roll(block.number + 1);
        uint64 cutoff = uint64(block.number - 1);
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.BALANCE_ATTESTATION_TYPEHASH,
                attestationDay,
                cutoff,
                uint64(block.timestamp),
                uint64(0),
                bytes32(0)
            )
        );
        bytes memory signature = sign(BANK_PK, structHash);
        vm.expectRevert(DonationLedger.StaleAttestation.selector);
        ledger.attestBalance(attestationDay, cutoff, uint64(block.timestamp), 0, 0, signature);

        uint64 day = attestationDay + 1;
        structHash = keccak256(
            abi.encode(
                VeritasTypes.BALANCE_ATTESTATION_TYPEHASH,
                day,
                uint64(block.number),
                uint64(block.timestamp),
                uint64(0),
                bytes32(0)
            )
        );
        signature = sign(BANK_PK, structHash);
        vm.expectRevert(DonationLedger.BadCutoff.selector);
        ledger.attestBalance(day, uint64(block.number), uint64(block.timestamp), 0, 0, signature);
    }

    function test_onlyTheBankAttests() public {
        vm.roll(block.number + 1);
        uint64 cutoff = uint64(block.number - 1);
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.BALANCE_ATTESTATION_TYPEHASH,
                uint64(1),
                cutoff,
                uint64(block.timestamp),
                uint64(0),
                bytes32(0)
            )
        );
        bytes memory signature = sign(RELAYER_PK, structHash);
        vm.expectRevert(abi.encodeWithSelector(Signatures.BadSignature.selector, bank));
        ledger.attestBalance(1, cutoff, uint64(block.timestamp), 0, 0, signature);
    }
}

contract ReceiptTest is Flows {
    MilestoneEscrow internal escrow;
    bytes16 internal pid;

    function setUp() public override {
        super.setUp();
        escrow = launchDefault(1);
        pid = escrow.projectId();
    }

    function test_mintByProofIsLockedAndIdempotent() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 1000));
        uint256 id = receipts.mint(p.batchId, p.leaf, p.proof);
        assertEq(id, receipts.receiptId(pid, donor(1)));
        assertEq(receipts.ownerOf(id), donor(1));
        assertTrue(receipts.locked(id));
        assertEq(receipts.holderCount(pid), 1);
        assertEq(receipts.mint(p.batchId, p.leaf, p.proof), id);
        assertEq(receipts.holderCount(pid), 1);
        assertTrue(receipts.supportsInterface(0xb45a3c0e));

        vm.prank(donor(1));
        vm.expectRevert(ReceiptToken.ReceiptsAreLocked.selector);
        receipts.transferFrom(donor(1), donor(2), id);
        vm.expectRevert(ReceiptToken.ReceiptsAreLocked.selector);
        receipts.approve(donor(2), id);
    }

    function test_noReceiptWithoutARealLeaf() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 1000));
        p.leaf.holder = donor(2);
        vm.expectRevert();
        receipts.mint(p.batchId, p.leaf, p.proof);
    }

    function test_rotationWaits48HoursAndOldKeyCanCancel() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 1000));
        uint256 id = receipts.mint(p.batchId, p.leaf, p.proof);
        address newKey = donor(7);

        vm.expectRevert(ReceiptToken.NotRelayer.selector);
        receipts.requestRotation(id, newKey);
        vm.prank(relayer);
        receipts.requestRotation(id, newKey);
        vm.expectRevert();
        receipts.finalizeRotation(id);

        uint64 readyAt = uint64(block.timestamp + 48 hours);
        bytes memory refusal = sign(
            donorKey(1),
            keccak256(abi.encode(VeritasTypes.ROTATION_CANCEL_TYPEHASH, id, newKey, readyAt))
        );
        receipts.cancelRotation(id, refusal);
        vm.warp(block.timestamp + 48 hours);
        vm.expectRevert(ReceiptToken.NoPendingRotation.selector);
        receipts.finalizeRotation(id);

        // The refusal named that request; it cannot refuse a later one to the same key.
        vm.prank(relayer);
        receipts.requestRotation(id, newKey);
        vm.expectRevert();
        receipts.cancelRotation(id, refusal);
        vm.warp(block.timestamp + 48 hours);
        receipts.finalizeRotation(id);
        assertEq(receipts.ownerOf(id), newKey);
        assertEq(receipts.controllerOf(pid, donor(1)), newKey);
    }

    function test_rotateBySigIsImmediateAndNotReplayable() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 1000));
        uint256 id = receipts.mint(p.batchId, p.leaf, p.proof);
        uint64 deadline = uint64(block.timestamp + 1 hours);
        bytes32 structHash = keccak256(
            abi.encode(VeritasTypes.KEY_ROTATION_TYPEHASH, id, donor(8), uint64(0), deadline)
        );
        bytes memory signature = sign(donorKey(1), structHash);
        receipts.rotateBySig(id, donor(8), deadline, signature);
        assertEq(receipts.ownerOf(id), donor(8));
        vm.expectRevert(); // nonce moved on and the owner changed
        receipts.rotateBySig(id, donor(8), deadline, signature);
    }

    function test_controllerDefaultsToTheHolder() public view {
        assertEq(receipts.controllerOf(pid, donor(3)), donor(3));
    }
}
