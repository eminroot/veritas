// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Flows} from "./Flows.t.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";
import {PassportRegistry} from "../src/PassportRegistry.sol";
import {BankPayoutVault} from "../src/BankPayoutVault.sol";
import {Allocation} from "../src/libraries/Allocation.sol";
import {
    DonationLeaf,
    LeafProof,
    ProjectConfig,
    VeritasTypes
} from "../src/libraries/VeritasTypes.sol";

contract StopTest is Flows {
    MilestoneEscrow internal escrow;
    MilestoneEscrow internal other;
    bytes16 internal pid;

    function setUp() public override {
        super.setUp();
        escrow = launchDefault(1);
        other = launchDefault(2);
        pid = escrow.projectId();
    }

    function refund(uint256 donorN, LeafProof[] memory proofs) internal {
        uint64 deadline = uint64(block.timestamp + 1 days);
        bytes memory signature = choiceSignature(
            donorKey(donorN),
            escrow,
            donor(donorN),
            VeritasTypes.CHOICE_REFUND,
            address(0),
            deadline
        );
        escrow.claim(
            donor(donorN), VeritasTypes.CHOICE_REFUND, address(0), deadline, proofs, signature
        );
    }

    function redirect(uint256 donorN, address target, LeafProof[] memory proofs) internal {
        uint64 deadline = uint64(block.timestamp + 1 days);
        bytes memory signature = choiceSignature(
            donorKey(donorN), escrow, donor(donorN), VeritasTypes.CHOICE_REDIRECT, target, deadline
        );
        escrow.claim(
            donor(donorN), VeritasTypes.CHOICE_REDIRECT, target, deadline, proofs, signature
        );
    }

    function refundExt(uint256 donorN, LeafProof[] memory proofs) external {
        refund(donorN, proofs);
    }

    function redirectExt(uint256 donorN, address target, LeafProof[] memory proofs) external {
        redirect(donorN, target, proofs);
    }

    function test_noClaimsWhileTheProjectRuns() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 1000));
        vm.expectRevert(MilestoneEscrow.NotEnded.selector);
        this.refundExt(1, one(p));
    }

    function test_withdrawnProjectRefundsDonors() public {
        LeafProof[] memory proofs =
            anchor(leaves2(makeLeaf(pid, donor(1), 0, 30_000), makeLeaf(pid, donor(1), 1, 70_000)));
        withdrawProject(escrow);
        assertEq(uint8(escrow.state()), uint8(MilestoneEscrow.State.Stopped));
        assertEq(uint8(escrow.stopReason()), uint8(MilestoneEscrow.StopReason.Withdrawn));

        LeafProof[] memory ordered = new LeafProof[](2);
        bool lower = hashLeaf(proofs[0].leaf) < hashLeaf(proofs[1].leaf);
        ordered[0] = lower ? proofs[0] : proofs[1];
        ordered[1] = lower ? proofs[1] : proofs[0];
        refund(1, ordered);
        assertEq(vazn.balanceOf(address(escrow)), 0);
        assertEq(vazn.balanceOf(address(vault)), 100_000);
        uint64 id = vault.lastInstructionId();
        BankPayoutVault.Instruction memory ins = vault.instruction(id);
        assertTrue(ins.isRefund);
        assertEq(ins.holder, donor(1));
        assertEq(ins.amount, 100_000);

        confirmPayout(id, 100_000);
        assertEq(vazn.totalSupply(), 0);

        vm.expectRevert(); // every leaf can be claimed once
        this.refundExt(1, one(proofs[0]));
    }

    function test_redirectMovesMoneyAndSplitsItByTheTargetsRule() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 1, 100_000));
        withdrawProject(escrow);
        redirect(1, address(other), one(p));
        assertEq(vazn.balanceOf(address(escrow)), 0);
        assertEq(vazn.balanceOf(address(other)), 100_000);
        // 100 000 qəpik over needs of 420 000, 1 383 000 and 246 000.
        assertEq(other.milestone(0).funded, 20_498);
        assertEq(other.milestone(1).funded, 67_496);
        assertEq(other.milestone(2).funded, 12_006);
    }

    function test_cannotRedirectToAStoppedOrUnknownProject() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 1000));
        withdrawProject(escrow);
        vm.expectRevert(MilestoneEscrow.BadTarget.selector);
        this.redirectExt(1, address(0xBAD), one(p));
        withdrawProject(other);
        vm.expectRevert(MilestoneEscrow.NotActive.selector);
        this.redirectExt(1, address(other), one(p));
    }

    function test_paidMilestonesAreSpentAndOnlyTheRestComesBack() public {
        LeafProof memory first = fundAndApprove(escrow, 0, 1, 420_000);
        LeafProof memory second = anchorOne(makeLeaf(pid, donor(1), 1, 50_000));
        attestBalanced();
        escrow.release(0);
        confirmPayout(escrow.milestone(0).payoutId, 420_000);
        withdrawProject(escrow);
        vm.expectRevert(MilestoneEscrow.NothingToClaim.selector);
        this.refundExt(1, one(first));
        refund(1, one(second));
        assertEq(vault.instruction(vault.lastInstructionId()).amount, 50_000);
    }

    function test_leftoverAfterACheaperPayoutIsShared() public {
        // Two donors fund milestone 0 fully; the invoice comes in 20% under budget.
        LeafProof[] memory proofs = anchor(
            leaves2(makeLeaf(pid, donor(1), 0, 300_000), makeLeaf(pid, donor(2), 0, 120_000))
        );
        submitEvidence(escrow, 0);
        recordChecks(escrow, 0, true);
        approveByOfficer(escrow, 0, 336_000);
        bytes32 id = openVote(escrow, 0, 2);
        castMilestoneVote(escrow, 0, 1, true, one(proofs[0]));
        vm.warp(block.timestamp + 72 hours);
        voting.close(id);
        attestBalanced();
        escrow.release(0);
        confirmPayout(escrow.milestone(0).payoutId, 336_000);
        withdrawProject(escrow);
        refund(1, one(proofs[0]));
        refund(2, one(proofs[1]));
        assertEq(vault.instruction(vault.lastInstructionId() - 1).amount, 60_000);
        assertEq(vault.instruction(vault.lastInstructionId()).amount, 24_000);
    }

    function test_noClaimWhileAPayoutIsInFlight() public {
        LeafProof memory p = fundAndApprove(escrow, 0, 1, 420_000);
        attestBalanced();
        escrow.release(0);
        withdrawProject(escrow);
        vm.expectRevert(abi.encodeWithSelector(MilestoneEscrow.PayoutInFlight.selector, 0));
        this.refundExt(1, one(p));
        failPayout(escrow.milestone(0).payoutId);
        refund(1, one(p)); // the failed payout came back, so the donor gets it all
        assertEq(vault.instruction(vault.lastInstructionId()).amount, 420_000);
    }

    function test_defaultRefundAfterTheChoiceWindow() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 9000));
        withdrawProject(escrow);
        vm.expectRevert(MilestoneEscrow.ChoiceWindowOpen.selector);
        escrow.claimDefault(donor(1), address(0), one(p));
        vm.warp(block.timestamp + 30 days + 1);
        escrow.claimDefault(donor(1), address(0), one(p)); // anyone may send a default refund
        assertEq(vault.instruction(vault.lastInstructionId()).amount, 9000);
    }

    function test_defaultRedirectGoesToTheSameCategoryAndOnlyByTheRelayer() public {
        ProjectConfig memory c = defaultConfig(projectIdOf(3));
        c.stop.unclaimedRedirects = true;
        MilestoneEscrow redirecting = launch(c);
        ProjectConfig memory health = defaultConfig(projectIdOf(4));
        health.category = 1;
        MilestoneEscrow elsewhere = launch(health);

        LeafProof memory p = anchorOne(makeLeaf(c.projectId, donor(1), 0, 9000));
        withdrawProject(redirecting);
        vm.warp(block.timestamp + 30 days + 1);
        vm.expectRevert(MilestoneEscrow.NotRelayer.selector);
        redirecting.claimDefault(donor(1), address(other), one(p));
        vm.prank(relayer);
        vm.expectRevert(MilestoneEscrow.WrongCategory.selector);
        redirecting.claimDefault(donor(1), address(elsewhere), one(p));
        vm.prank(relayer);
        redirecting.claimDefault(donor(1), address(other), one(p));
        assertEq(vazn.balanceOf(address(other)), 9000);
    }

    function test_aFailedRefundCanBeChosenAgain() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 9000));
        withdrawProject(escrow);
        refund(1, one(p));
        failPayout(vault.lastInstructionId()); // the card expired
        assertEq(escrow.retryBalance(donor(1)), 9000);
        redirect(1, address(other), new LeafProof[](0));
        assertEq(escrow.retryBalance(donor(1)), 0);
        assertEq(vazn.balanceOf(address(other)), 9000);
    }

    function test_missedEvidenceDeadlineLetsAnyoneStop() public {
        vm.expectRevert(MilestoneEscrow.DeadlineNotPassed.selector);
        escrow.stopForMissedDeadline(0);
        vm.warp(escrow.milestone(0).evidenceDeadline + 1);
        escrow.stopForMissedDeadline(0);
        assertEq(uint8(escrow.stopReason()), uint8(MilestoneEscrow.StopReason.MissedDeadline));
    }

    function test_stopVoteProposedByTheOfficer() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 2, 5000));
        receipts.mint(p.batchId, p.leaf, p.proof);
        bytes32 reason = keccak256("contractor vanished");
        bytes32 structHash =
            keccak256(abi.encode(VeritasTypes.STOP_PROPOSAL_TYPEHASH, pid, uint32(1), reason));
        escrow.proposeStop(reason, sign(OFFICER_PK, structHash));
        vm.prank(relayer);
        escrow.openStopVote(1);
        bytes32 id = voting.ballotId(address(escrow), VeritasTypes.BALLOT_STOP, 0, 1);
        bytes memory signature =
            voteSignature(donorKey(1), pid, donor(1), VeritasTypes.BALLOT_STOP, 0, 1, true);
        voting.castVoteBySig(id, donor(1), true, one(p), signature); // any milestone counts
        vm.warp(block.timestamp + 72 hours);
        voting.close(id);
        assertEq(uint8(escrow.stopReason()), uint8(MilestoneEscrow.StopReason.Vote));
    }

    function test_amendmentChangesTheContractorOnlyAfterAVote() public {
        LeafProof memory p = anchorOne(makeLeaf(pid, donor(1), 0, 5000));
        receipts.mint(p.batchId, p.leaf, p.proof);
        bytes32 newPassport = keccak256("passport v2");
        bytes32 newContractor = keccak256("veritas:contractor:1300000039");
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.AMENDMENT_TYPEHASH,
                pid,
                uint32(2),
                newPassport,
                keccak256(bytes("bafy-v2")),
                newContractor
            )
        );
        registry.proposeAmendment(
            pid, 2, newPassport, "bafy-v2", newContractor, sign(CHARITY_PK, structHash)
        );
        assertEq(registry.contractorHashOf(pid), CONTRACTOR);
        vm.prank(relayer);
        registry.openAmendmentVote(pid, 1);
        bytes32 id = voting.ballotId(address(escrow), VeritasTypes.BALLOT_AMENDMENT, 0, 1);
        bytes memory signature =
            voteSignature(donorKey(1), pid, donor(1), VeritasTypes.BALLOT_AMENDMENT, 0, 1, true);
        voting.castVoteBySig(id, donor(1), true, one(p), signature);
        vm.warp(block.timestamp + 72 hours);
        voting.close(id);
        PassportRegistry.Entry memory entry = registry.current(pid);
        assertEq(entry.version, 2);
        assertEq(entry.passportHash, newPassport);
        assertEq(entry.contractorHash, newContractor);
    }

    function test_anAmendmentWithoutVotesFails() public {
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.AMENDMENT_TYPEHASH,
                pid,
                uint32(2),
                keccak256("v2"),
                keccak256(bytes("cid")),
                keccak256("c2")
            )
        );
        registry.proposeAmendment(
            pid, 2, keccak256("v2"), "cid", keccak256("c2"), sign(CHARITY_PK, structHash)
        );
        vm.prank(relayer);
        registry.openAmendmentVote(pid, 0);
        bytes32 id = voting.ballotId(address(escrow), VeritasTypes.BALLOT_AMENDMENT, 0, 1);
        vm.warp(block.timestamp + 72 hours);
        voting.close(id);
        assertEq(registry.versionOf(pid), 1);
        assertEq(registry.pendingAmendment(pid).version, 0);
    }
}

contract AllocationHarness {
    function allocate(uint64 amount, uint64[] memory remaining, uint8 rule)
        external
        pure
        returns (uint64[] memory)
    {
        return Allocation.allocate(amount, remaining, rule);
    }
}

contract AllocationTest is Flows {
    AllocationHarness internal harness = new AllocationHarness();

    function test_proRataLikePython() public view {
        uint64[] memory remaining = new uint64[](3);
        remaining[0] = 1000;
        remaining[1] = 1000;
        remaining[2] = 1000;
        uint64[] memory parts = harness.allocate(101, remaining, 0);
        assertEq(parts[0], 34);
        assertEq(parts[1], 34);
        assertEq(parts[2], 33);
    }

    function test_sequentialFillsInOrder() public view {
        uint64[] memory remaining = new uint64[](3);
        remaining[0] = 50_000;
        remaining[1] = 30_000;
        remaining[2] = 20_000;
        uint64[] memory parts = harness.allocate(70_000, remaining, 1);
        assertEq(parts[0], 50_000);
        assertEq(parts[1], 20_000);
        assertEq(parts[2], 0);
    }

    function test_overfundingIsRefused() public {
        uint64[] memory remaining = new uint64[](2);
        remaining[0] = 10;
        vm.expectRevert(abi.encodeWithSelector(Allocation.Overfunded.selector, 11, 10));
        harness.allocate(11, remaining, 0);
    }

    function testFuzz_partsAddUpAndNeverExceedNeeds(
        uint64 amountSeed,
        uint64[6] memory needs,
        bool sequential
    ) public view {
        uint64[] memory remaining = new uint64[](6);
        uint256 total;
        for (uint256 i = 0; i < 6; i++) {
            remaining[i] = needs[i] % 2 == 0 ? 0 : uint64(bound(needs[i], 1, 1e12));
            total += remaining[i];
        }
        vm.assume(total > 0);
        uint64 amount = uint64(bound(amountSeed, 1, total));
        uint64[] memory parts = harness.allocate(amount, remaining, sequential ? 1 : 0);
        uint256 sum;
        for (uint256 i = 0; i < 6; i++) {
            assertLe(parts[i], remaining[i]);
            sum += parts[i];
        }
        assertEq(sum, amount);
    }
}
