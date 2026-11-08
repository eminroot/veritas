// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Flows} from "./Flows.t.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";
import {BankPayoutVault} from "../src/BankPayoutVault.sol";
import {VotingModule} from "../src/VotingModule.sol";
import {Signatures} from "../src/libraries/Signatures.sol";
import {
    DecisionRules,
    DonationLeaf,
    LeafProof,
    VeritasTypes
} from "../src/libraries/VeritasTypes.sol";

contract MilestoneFlowTest is Flows {
    MilestoneEscrow internal escrow;
    bytes16 internal pid;

    function setUp() public override {
        super.setUp();
        escrow = launchDefault(1);
        pid = escrow.projectId();
    }

    function status(uint8 index) internal view returns (MilestoneEscrow.Status) {
        return escrow.milestone(index).status;
    }

    /// The whole road: fund, evidence, checks, officer, vote, release, payout, burn.
    function test_aWholeMilestone() public {
        LeafProof[] memory proofs = anchor(
            leaves2(makeLeaf(pid, donor(1), 0, 300_000), makeLeaf(pid, donor(2), 0, 120_000))
        );
        assertEq(vazn.totalSupply(), 420_000);

        uint32 attempt = submitEvidence(escrow, 0);
        assertEq(attempt, 1);
        assertEq(uint8(status(0)), uint8(MilestoneEscrow.Status.EvidenceSubmitted));
        recordChecks(escrow, 0, true);
        assertEq(uint8(status(0)), uint8(MilestoneEscrow.Status.Checked));
        approveByOfficer(escrow, 0, 400_000);
        assertEq(uint8(status(0)), uint8(MilestoneEscrow.Status.OfficerApproved));

        receipts.mint(proofs[0].batchId, proofs[0].leaf, proofs[0].proof);
        receipts.mint(proofs[1].batchId, proofs[1].leaf, proofs[1].proof);
        bytes32 id = openVote(escrow, 0, 2);
        assertEq(uint8(status(0)), uint8(MilestoneEscrow.Status.Voting));
        castMilestoneVote(escrow, 0, 1, true, one(proofs[0]));
        castMilestoneVote(escrow, 0, 2, false, one(proofs[1]));
        vm.expectRevert(
            abi.encodeWithSelector(VotingModule.StillOpen.selector, voting.ballot(id).end)
        );
        voting.close(id);
        vm.warp(block.timestamp + 72 hours);
        // One yes and one no is not more than half, so the vote fails and the milestone goes back.
        voting.close(id);
        assertEq(uint8(status(0)), uint8(MilestoneEscrow.Status.Rejected));

        // The charity resubmits, the officer approves again, and this time the donors agree.
        attempt = submitEvidence(escrow, 0);
        assertEq(attempt, 2);
        recordChecks(escrow, 0, true);
        approveByOfficer(escrow, 0, 400_000);
        id = openVote(escrow, 0, 2);
        castMilestoneVote(escrow, 0, 1, true, one(proofs[0]));
        castMilestoneVote(escrow, 0, 2, true, one(proofs[1]));
        vm.warp(block.timestamp + 72 hours);
        voting.close(id);
        assertEq(uint8(status(0)), uint8(MilestoneEscrow.Status.Approved));

        attestBalanced();
        escrow.release(0);
        MilestoneEscrow.Milestone memory m = escrow.milestone(0);
        assertEq(uint8(m.status), uint8(MilestoneEscrow.Status.Released));
        assertEq(m.released, 400_000);
        assertEq(vazn.balanceOf(address(vault)), 400_000);
        BankPayoutVault.Instruction memory ins = vault.instruction(m.payoutId);
        assertEq(ins.amount, 400_000);
        assertEq(ins.contractorHash, CONTRACTOR);
        assertEq(ins.invoiceHash, INVOICE);

        confirmPayout(m.payoutId, 400_000);
        assertEq(uint8(status(0)), uint8(MilestoneEscrow.Status.Paid));
        assertEq(vazn.totalSupply(), 20_000);
        assertEq(vazn.balanceOf(address(escrow)), 20_000);
    }

    function test_releaseNeedsAllItsConditions() public {
        fundAndApprove(escrow, 0, 1, 420_000);
        vm.expectRevert(MilestoneEscrow.ReleasesStopped.selector);
        escrow.release(0); // no attestation yet
        attestBalanced();
        vm.prank(admin);
        hub.setReleasesPaused(true);
        vm.expectRevert(MilestoneEscrow.ReleasesStopped.selector);
        escrow.release(0);
        vm.prank(admin);
        hub.setReleasesPaused(false);
        vm.expectRevert(
            abi.encodeWithSelector(
                MilestoneEscrow.WrongStatus.selector, MilestoneEscrow.Status.Funding
            )
        );
        escrow.release(1);
        escrow.release(0);
    }

    function test_releaseNeedsTheMoneyToBeThere() public {
        // Approved for the full budget, but only part of it was raised.
        anchorOne(makeLeaf(pid, donor(1), 0, 100_000));
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(2), 0, 1000));
        submitEvidence(escrow, 0);
        recordChecks(escrow, 0, true);
        approveByOfficer(escrow, 0, 420_000);
        bytes32 id = openVote(escrow, 0, 1);
        castMilestoneVote(escrow, 0, 2, true, one(p));
        vm.warp(block.timestamp + 72 hours);
        voting.close(id);
        attestBalanced();
        vm.expectRevert(MilestoneEscrow.InsufficientFunds.selector);
        escrow.release(0);
    }

    function test_failedPayoutComesBackAndCanBeReleasedAgain() public {
        fundAndApprove(escrow, 0, 1, 420_000);
        attestBalanced();
        escrow.release(0);
        uint64 first = escrow.milestone(0).payoutId;
        failPayout(first);
        assertEq(uint8(status(0)), uint8(MilestoneEscrow.Status.Approved));
        assertEq(escrow.milestone(0).released, 0);
        assertEq(vazn.balanceOf(address(escrow)), 420_000);
        vm.expectRevert(abi.encodeWithSelector(BankPayoutVault.NotPending.selector, first));
        this.confirmPayoutExt(first, 420_000);

        escrow.release(0);
        uint64 second = escrow.milestone(0).payoutId;
        assertGt(second, first);
        confirmPayout(second, 420_000);
        assertEq(uint8(status(0)), uint8(MilestoneEscrow.Status.Paid));
    }

    function test_onlyTheBankConfirmsPayouts() public {
        fundAndApprove(escrow, 0, 1, 420_000);
        attestBalanced();
        escrow.release(0);
        uint64 id = escrow.milestone(0).payoutId;
        bytes32 structHash = keccak256(
            abi.encode(VeritasTypes.PAYOUT_CONFIRMATION_TYPEHASH, id, uint64(420_000), bytes32(0))
        );
        bytes memory signature = sign(RELAYER_PK, structHash);
        vm.expectRevert(abi.encodeWithSelector(Signatures.BadSignature.selector, bank));
        vault.confirm(id, bytes32(0), signature);
    }

    function test_failedChecksNeedAnOverrideWithAReason() public {
        anchorOne(makeLeaf(pid, donor(1), 0, 420_000));
        submitEvidence(escrow, 0);
        recordChecks(escrow, 0, false);
        (MilestoneEscrow.Decision memory d, bytes memory signature) =
            decision(escrow, 0, true, 420_000, false, bytes32(0));
        vm.expectRevert(MilestoneEscrow.BadDecision.selector);
        escrow.officerDecide(d, signature);
        (d, signature) = decision(escrow, 0, true, 420_000, true, bytes32(0));
        vm.expectRevert(MilestoneEscrow.BadDecision.selector);
        escrow.officerDecide(d, signature);
        (d, signature) = decision(escrow, 0, true, 420_000, true, keccak256("reason"));
        escrow.officerDecide(d, signature);
        assertEq(uint8(status(0)), uint8(MilestoneEscrow.Status.OfficerApproved));
    }

    function test_aRejectionGivesTheCharityAResubmissionDeadline() public {
        submitEvidence(escrow, 0);
        recordChecks(escrow, 0, true);
        (MilestoneEscrow.Decision memory d, bytes memory signature) =
            decision(escrow, 0, false, 0, false, bytes32(0));
        vm.expectRevert(MilestoneEscrow.BadDecision.selector);
        escrow.officerDecide(d, signature); // a rejection has to say why
        (d, signature) = decision(escrow, 0, false, 0, false, keccak256("photos blurred"));
        escrow.officerDecide(d, signature);
        MilestoneEscrow.Milestone memory m = escrow.milestone(0);
        assertEq(uint8(m.status), uint8(MilestoneEscrow.Status.Rejected));
        assertEq(m.resubmitDeadline, m.evidenceDeadline); // the original deadline is later

        vm.warp(m.resubmitDeadline + 1);
        vm.expectRevert(MilestoneEscrow.DeadlinePassed.selector);
        this.submitAgain();
    }

    function submitAgain() external {
        submitEvidence(escrow, 0);
    }

    function test_decisionIsBoundToTheEvidenceTheOfficerSaw() public {
        submitEvidence(escrow, 0);
        recordChecks(escrow, 0, true);
        (MilestoneEscrow.Decision memory d, bytes memory signature) =
            decision(escrow, 0, true, 420_000, false, bytes32(0));
        d.amount = 419_999;
        vm.expectRevert(abi.encodeWithSelector(Signatures.BadSignature.selector, officer));
        escrow.officerDecide(d, signature);
    }

    function test_onlyTheRelayerAnchorsEvidenceAndChecks() public {
        bytes32 bundle = bundleOf(0, 1);
        bytes memory signature = sign(
            CHARITY_PK,
            keccak256(abi.encode(VeritasTypes.EVIDENCE_TYPEHASH, pid, uint8(0), uint32(1), bundle))
        );
        vm.expectRevert(MilestoneEscrow.NotRelayer.selector);
        escrow.submitEvidence(0, bundle, "cid", signature);
        vm.prank(relayer);
        vm.expectRevert(abi.encodeWithSelector(Signatures.BadSignature.selector, charity));
        escrow.submitEvidence(0, keccak256("other bundle"), "cid", signature);
        vm.prank(relayer);
        escrow.submitEvidence(0, bundle, "cid", signature);
        vm.expectRevert(MilestoneEscrow.NotRelayer.selector);
        escrow.recordChecks(0, 1, REPORT, true);
    }

    function test_completingEveryMilestoneCompletesTheProject() public {
        uint64[3] memory budgets = [uint64(420_000), 1_383_000, 246_000];
        for (uint8 i = 0; i < 3; i++) {
            fundAndApprove(escrow, i, 1 + i, budgets[i]);
            attestBalanced();
            escrow.release(i);
            confirmPayout(escrow.milestone(i).payoutId, budgets[i]);
        }
        assertEq(uint8(escrow.state()), uint8(MilestoneEscrow.State.Completed));
        assertEq(vazn.totalSupply(), 0);

        bytes32 report = keccak256("completion report");
        bytes32 structHash = keccak256(
            abi.encode(VeritasTypes.COMPLETION_TYPEHASH, pid, report, keccak256(bytes("bafy-done")))
        );
        escrow.recordCompletion(report, "bafy-done", sign(CHARITY_PK, structHash));
        assertTrue(escrow.completionRecorded());
    }
}

contract VotingTest is Flows {
    MilestoneEscrow internal escrow;
    bytes16 internal pid;

    function setUp() public override {
        super.setUp();
        escrow = launchDefault(1);
        pid = escrow.projectId();
    }

    function readyToVote(uint32 eligible) internal returns (bytes32) {
        submitEvidence(escrow, 0);
        recordChecks(escrow, 0, true);
        approveByOfficer(escrow, 0, 100_000);
        return openVote(escrow, 0, eligible);
    }

    function test_eligibilityNeedsLeavesForThatMilestone() public {
        LeafProof memory wrongMilestone = anchorOne(makeLeaf(pid, donor(1), 1, 5000));
        LeafProof memory small = anchorOne(makeLeaf(pid, donor(2), 0, 400));
        LeafProof memory small2 = anchorOne(makeLeaf(pid, donor(2), 0, 300));
        readyToVote(10);
        vm.expectRevert(VotingModule.WrongLeaf.selector);
        this.castMilestoneVoteExt(escrow, 0, 1, true, one(wrongMilestone));
        vm.expectRevert(abi.encodeWithSelector(VotingModule.BelowMinimum.selector, 400, 500));
        this.castMilestoneVoteExt(escrow, 0, 2, true, one(small));

        // Two small donations add up to the minimum, given in leaf-hash order.
        LeafProof[] memory both = new LeafProof[](2);
        bool firstLower = hashLeaf(small.leaf) < hashLeaf(small2.leaf);
        both[0] = firstLower ? small : small2;
        both[1] = firstLower ? small2 : small;
        LeafProof[] memory reversed = new LeafProof[](2);
        reversed[0] = both[1];
        reversed[1] = both[0];
        vm.expectRevert(VotingModule.DuplicateLeaf.selector);
        this.castMilestoneVoteExt(escrow, 0, 2, true, reversed);
        castMilestoneVote(escrow, 0, 2, true, both);
    }

    function test_oneVotePerDonorAndOnlyTheirKey() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 5000));
        bytes32 id = readyToVote(1);
        bytes memory forged =
            voteSignature(donorKey(9), pid, donor(1), VeritasTypes.BALLOT_MILESTONE, 0, 1, true);
        vm.expectRevert(abi.encodeWithSelector(Signatures.BadSignature.selector, donor(1)));
        voting.castVoteBySig(id, donor(1), true, one(p), forged);
        castMilestoneVote(escrow, 0, 1, true, one(p));
        vm.expectRevert(abi.encodeWithSelector(VotingModule.AlreadyVoted.selector, donor(1)));
        this.castMilestoneVoteExt(escrow, 0, 1, true, one(p));
    }

    function test_aRotatedKeyVotesForTheHolder() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 5000));
        uint256 receipt = receipts.mint(p.batchId, p.leaf, p.proof);
        vm.prank(relayer);
        receipts.requestRotation(receipt, donor(5));
        vm.warp(block.timestamp + 48 hours);
        receipts.finalizeRotation(receipt);
        bytes32 id = readyToVote(1);
        bytes memory signature =
            voteSignature(donorKey(5), pid, donor(1), VeritasTypes.BALLOT_MILESTONE, 0, 1, true);
        voting.castVoteBySig(id, donor(1), true, one(p), signature);
        assertTrue(voting.hasVoted(id, donor(1)));
    }

    function test_lowTurnoutExtendsOnceThenTheOfficerDecisionStands() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 5000));
        receipts.mint(p.batchId, p.leaf, p.proof);
        for (uint256 i = 2; i <= 12; i++) {
            LeafProof memory q = anchorOne(makeLeaf(pid, donor(i), 0, 500));
            receipts.mint(q.batchId, q.leaf, q.proof);
        }
        bytes32 id = readyToVote(12);
        castMilestoneVote(escrow, 0, 1, false, one(p)); // 1 of 12 is below 10% turnout
        vm.warp(block.timestamp + 72 hours);
        voting.close(id);
        assertTrue(voting.ballot(id).extended);
        assertEq(uint8(escrow.milestone(0).status), uint8(MilestoneEscrow.Status.Voting));
        vm.warp(block.timestamp + 48 hours);
        voting.close(id);
        assertTrue(voting.ballot(id).passed);
        assertEq(uint8(escrow.milestone(0).status), uint8(MilestoneEscrow.Status.Approved));
    }

    function test_theEligibleCountIsCappedByReceipts() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 5000));
        receipts.mint(p.batchId, p.leaf, p.proof);
        bytes32 id = readyToVote(1000); // an inflated count cannot make turnout look low
        assertEq(voting.ballot(id).eligible, 1);
        castMilestoneVote(escrow, 0, 1, false, one(p));
        vm.warp(block.timestamp + 72 hours);
        voting.close(id);
        assertFalse(voting.ballot(id).passed);
        assertEq(uint8(escrow.milestone(0).status), uint8(MilestoneEscrow.Status.Rejected));
    }

    function test_votesStopAtTheEndOfTheWindow() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 5000));
        bytes32 id = readyToVote(1);
        vm.warp(block.timestamp + 72 hours);
        vm.expectRevert(abi.encodeWithSelector(VotingModule.VotingClosed.selector, id));
        this.castMilestoneVoteExt(escrow, 0, 1, true, one(p));
    }

    function test_onlyEscrowsOpenVotes() public {
        DecisionRules memory rules = escrow.rules();
        vm.expectRevert(VotingModule.NotAllowed.selector);
        voting.open(pid, 0, 0, 1, 1, rules);
    }
}
