// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Flows} from "./Flows.t.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";
import {DonationLeaf, LeafProof, VeritasTypes} from "../src/libraries/VeritasTypes.sol";

/// @notice Money cannot be claimed twice or out of thin air, whatever the amounts.
contract ClaimFuzzTest is Flows {
    function _refund(MilestoneEscrow escrow, uint256 donorN, LeafProof memory proof) internal {
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
            donor(donorN), VeritasTypes.CHOICE_REFUND, address(0), deadline, one(proof), signature
        );
    }

    /// Several donors fund milestone 0, it is paid out for some amount up to what it raised,
    /// the project stops, and every donor takes a refund. Each gets exactly their share of
    /// the leftover, rounded down, and together they never take more than the escrow holds.
    function testFuzz_sharesOfWhatIsLeftAreExact(
        uint64[4] memory seeds,
        uint64 releaseSeed,
        uint8 count
    ) public {
        MilestoneEscrow escrow = launchDefault(1);
        bytes16 pid = escrow.projectId();
        uint256 donors = bound(count, 1, 4);
        DonationLeaf[] memory leaves = new DonationLeaf[](donors);
        uint256 funded;
        for (uint256 i = 0; i < donors; i++) {
            uint64 amount = uint64(bound(seeds[i], 1, 100_000));
            leaves[i] = makeLeaf(pid, donor(i + 1), 0, amount);
            funded += amount;
        }
        LeafProof[] memory proofs = anchor(leaves);

        uint64 released = uint64(bound(releaseSeed, 1, funded));
        submitEvidence(escrow, 0);
        recordChecks(escrow, 0, true);
        approveByOfficer(escrow, 0, released);
        bytes32 ballot = openVote(escrow, 0, 0);
        vm.warp(block.timestamp + 72 hours);
        voting.close(ballot); // nobody could vote, so the officer's decision stands
        attestBalanced();
        escrow.release(0);
        confirmPayout(escrow.milestone(0).payoutId, released);
        withdrawProject(escrow);

        uint256 left = funded - released;
        uint256 refunded;
        for (uint256 i = 0; i < donors; i++) {
            uint256 share = uint256(leaves[i].amount) * left / funded;
            if (share == 0) {
                vm.expectRevert(MilestoneEscrow.NothingToClaim.selector);
                this.refundExt(escrow, i + 1, proofs[i]);
                continue;
            }
            _refund(escrow, i + 1, proofs[i]);
            assertEq(vault.instruction(vault.lastInstructionId()).amount, share);
            refunded += share;
        }
        assertLe(refunded, left);
        assertEq(vazn.balanceOf(address(escrow)), left - refunded);
        assertLt(left - refunded, donors); // at most one qəpik of rounding per donor stays
    }

    function refundExt(MilestoneEscrow escrow, uint256 donorN, LeafProof memory proof) external {
        _refund(escrow, donorN, proof);
    }
}
