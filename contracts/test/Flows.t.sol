// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Base} from "./Base.t.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";
import {DonationLeaf, LeafProof, VeritasTypes} from "../src/libraries/VeritasTypes.sol";

/// @notice Helpers that walk a milestone through its states the way the backend will.
abstract contract Flows is Base {
    bytes32 internal constant REPORT = keccak256("check report");
    bytes32 internal constant INVOICE = keccak256("invoice 0001");

    function bundleOf(uint8 index, uint32 attempt) internal pure returns (bytes32) {
        return keccak256(abi.encode("bundle", index, attempt));
    }

    function submitEvidence(MilestoneEscrow e, uint8 index) internal returns (uint32 attempt) {
        attempt = e.milestone(index).attempt + 1;
        bytes32 bundle = bundleOf(index, attempt);
        bytes32 structHash = keccak256(
            abi.encode(VeritasTypes.EVIDENCE_TYPEHASH, e.projectId(), index, attempt, bundle)
        );
        bytes memory signature = sign(CHARITY_PK, structHash);
        vm.prank(relayer);
        e.submitEvidence(index, bundle, "bafy-evidence", signature);
    }

    function recordChecks(MilestoneEscrow e, uint8 index, bool passed) internal {
        uint32 attempt = e.milestone(index).attempt;
        vm.prank(relayer);
        e.recordChecks(index, attempt, REPORT, passed);
    }

    function decision(
        MilestoneEscrow e,
        uint8 index,
        bool approve,
        uint64 amount,
        bool overrideChecks,
        bytes32 reasonHash
    ) internal view returns (MilestoneEscrow.Decision memory d, bytes memory signature) {
        MilestoneEscrow.Milestone memory m = e.milestone(index);
        d = MilestoneEscrow.Decision({
            milestone: index,
            attempt: m.attempt,
            approve: approve,
            invoiceHash: approve ? INVOICE : bytes32(0),
            amount: approve ? amount : 0,
            overrideChecks: overrideChecks,
            reasonHash: reasonHash
        });
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.DECISION_TYPEHASH,
                e.projectId(),
                d.milestone,
                d.attempt,
                d.approve,
                m.bundleHash,
                m.reportHash,
                d.invoiceHash,
                d.amount,
                d.overrideChecks,
                d.reasonHash
            )
        );
        signature = sign(OFFICER_PK, structHash);
    }

    function approveByOfficer(MilestoneEscrow e, uint8 index, uint64 amount) internal {
        (MilestoneEscrow.Decision memory d, bytes memory signature) =
            decision(e, index, true, amount, false, bytes32(0));
        e.officerDecide(d, signature);
    }

    function openVote(MilestoneEscrow e, uint8 index, uint32 eligible)
        internal
        returns (bytes32 ballotId)
    {
        vm.prank(relayer);
        e.openMilestoneVote(index, eligible);
        ballotId = voting.ballotId(
            address(e), VeritasTypes.BALLOT_MILESTONE, index, e.milestone(index).attempt
        );
    }

    function voteSignature(
        uint256 donorPk,
        bytes16 projectId,
        address holder,
        uint8 kind,
        uint8 index,
        uint32 round,
        bool approve
    ) internal view returns (bytes memory) {
        bytes32 structHash = keccak256(
            abi.encode(VeritasTypes.VOTE_TYPEHASH, projectId, holder, kind, index, round, approve)
        );
        return sign(donorPk, structHash);
    }

    function castMilestoneVote(
        MilestoneEscrow e,
        uint8 index,
        uint256 donorN,
        bool approve,
        LeafProof[] memory proofs
    ) internal {
        uint32 round = e.milestone(index).attempt;
        bytes32 id = voting.ballotId(address(e), VeritasTypes.BALLOT_MILESTONE, index, round);
        bytes memory signature = voteSignature(
            donorKey(donorN),
            e.projectId(),
            donor(donorN),
            VeritasTypes.BALLOT_MILESTONE,
            index,
            round,
            approve
        );
        voting.castVoteBySig(id, donor(donorN), approve, proofs, signature);
    }

    /// Funds a milestone with one donor's leaf, then takes it to Approved through the officer
    /// and a vote that passes with that donor's yes.
    function fundAndApprove(MilestoneEscrow e, uint8 index, uint256 donorN, uint64 amount)
        internal
        returns (LeafProof memory proof)
    {
        proof = anchorOne(makeLeaf(e.projectId(), donor(donorN), index, amount));
        submitEvidence(e, index);
        recordChecks(e, index, true);
        approveByOfficer(e, index, amount);
        bytes32 id = openVote(e, index, 1);
        castMilestoneVote(e, index, donorN, true, one(proof));
        vm.warp(block.timestamp + 72 hours);
        voting.close(id);
    }

    // External wrappers, so vm.expectRevert can target a helper that makes several calls.
    function castMilestoneVoteExt(
        MilestoneEscrow e,
        uint8 index,
        uint256 donorN,
        bool approve,
        LeafProof[] memory proofs
    ) external {
        castMilestoneVote(e, index, donorN, approve, proofs);
    }

    function confirmPayoutExt(uint64 instructionId, uint64 amount) external {
        confirmPayout(instructionId, amount);
    }

    function confirmPayout(uint64 instructionId, uint64 amount) internal {
        bytes32 paymentRef = keccak256(abi.encode("bank ref", instructionId));
        bytes32 structHash = keccak256(
            abi.encode(VeritasTypes.PAYOUT_CONFIRMATION_TYPEHASH, instructionId, amount, paymentRef)
        );
        vault.confirm(instructionId, paymentRef, sign(BANK_PK, structHash));
    }

    function failPayout(uint64 instructionId) internal {
        bytes32 reason = keccak256("account closed");
        bytes32 structHash =
            keccak256(abi.encode(VeritasTypes.PAYOUT_FAILURE_TYPEHASH, instructionId, reason));
        vault.fail(instructionId, reason, sign(BANK_PK, structHash));
    }

    function choiceSignature(
        uint256 donorPk,
        MilestoneEscrow e,
        address holder,
        uint8 action,
        address target,
        uint64 deadline
    ) internal view returns (bytes memory) {
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.CHOICE_TYPEHASH,
                e.projectId(),
                holder,
                action,
                target,
                e.claimNonce(holder),
                deadline
            )
        );
        return sign(donorPk, structHash);
    }

    function withdrawProject(MilestoneEscrow e) internal {
        bytes32 reason = keccak256("charity withdraws");
        bytes32 structHash =
            keccak256(abi.encode(VeritasTypes.WITHDRAW_TYPEHASH, e.projectId(), reason));
        e.withdraw(reason, sign(CHARITY_PK, structHash));
    }

    function leaves1(DonationLeaf memory a) internal pure returns (DonationLeaf[] memory list) {
        list = new DonationLeaf[](1);
        list[0] = a;
    }

    function leaves2(DonationLeaf memory a, DonationLeaf memory b)
        internal
        pure
        returns (DonationLeaf[] memory list)
    {
        list = new DonationLeaf[](2);
        list[0] = a;
        list[1] = b;
    }
}
