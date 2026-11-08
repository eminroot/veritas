// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {DecisionRules, LeafProof, VeritasTypes} from "./libraries/VeritasTypes.sol";
import {Signatures} from "./libraries/Signatures.sol";
import {
    IBallotCallback,
    IDonationLedger,
    IReceiptToken,
    IVeritasHub
} from "./interfaces/IVeritas.sol";

/// @title VotingModule
/// @notice Milestone, amendment and stop votes for every project.
/// @dev One donor, one vote. A donor proves eligibility with their own leaves from settled
/// batches: for a milestone vote, leaves for that milestone adding up to at least the
/// Passport's minimum; for an amendment or stop vote, leaves for any milestone of the project.
/// The contract learns the donor's per-project key and nothing else. The vote is signed by the
/// key that controls that holder (see ReceiptToken), and anyone may submit it.
///
/// The number of eligible voters is a Veritas claim made when the vote opens. It only sets the
/// turnout. It is capped at the number of donors with a receipt for the project, a vote never
/// counts fewer voters than have actually voted, and every vote runs its full window, so no
/// count can cut donors out of a vote.
contract VotingModule {
    struct Ballot {
        address escrow;
        address callback;
        bytes16 projectId;
        uint8 kind;
        uint8 milestone;
        uint32 round;
        uint64 end;
        uint32 eligible;
        uint32 yes;
        uint32 no;
        uint32 extension;
        uint16 minTurnoutBps;
        uint16 approvalBps;
        uint64 minVoteAmount;
        bool fallbackApproves;
        bool extended;
        bool closed;
        bool passed;
    }

    IVeritasHub public immutable hub;
    mapping(bytes32 => Ballot) private _ballots;
    mapping(bytes32 => mapping(address => bool)) public hasVoted;

    event VoteOpened(
        bytes32 indexed ballotId,
        bytes16 indexed projectId,
        uint8 kind,
        uint8 milestone,
        uint32 round,
        uint64 end,
        uint32 eligible
    );
    event VoteCast(bytes32 indexed ballotId, address indexed holder, bool approve, uint64 weight);
    event VoteExtended(bytes32 indexed ballotId, uint64 end);
    event VoteClosed(
        bytes32 indexed ballotId, bool passed, uint32 yes, uint32 no, bool turnoutFallback
    );

    error NotAllowed();
    error BallotExists(bytes32 ballotId);
    error UnknownBallot(bytes32 ballotId);
    error VotingClosed(bytes32 ballotId);
    error StillOpen(uint64 end);
    error AlreadyVoted(address holder);
    error WrongLeaf();
    error DuplicateLeaf();
    error BelowMinimum(uint256 amount, uint64 minimum);

    constructor(IVeritasHub hub_) {
        hub = hub_;
    }

    function ballotId(address escrow, uint8 kind, uint8 milestone, uint32 round)
        public
        pure
        returns (bytes32)
    {
        return keccak256(abi.encode(escrow, kind, milestone, round));
    }

    function ballot(bytes32 id) external view returns (Ballot memory) {
        return _ballots[id];
    }

    /// @notice Called by a project's escrow, or by the registry for an amendment vote. Rules
    /// are copied, so the vote runs on the rules that were in force when it opened.
    function open(
        bytes16 projectId,
        uint8 kind,
        uint8 milestone,
        uint32 round,
        uint32 eligible,
        DecisionRules calldata rules
    ) external returns (bytes32 id) {
        address escrow = hub.escrowOf(projectId);
        bool allowed = msg.sender == escrow
            || (kind == VeritasTypes.BALLOT_AMENDMENT && msg.sender == hub.registry());
        if (escrow == address(0) || !allowed) revert NotAllowed();
        id = ballotId(escrow, kind, milestone, round);
        if (_ballots[id].escrow != address(0)) revert BallotExists(id);
        uint32 holders = IReceiptToken(hub.receipts()).holderCount(projectId);
        if (eligible > holders) eligible = holders;
        uint64 end = uint64(block.timestamp + rules.voteWindow);
        _ballots[id] = Ballot({
            escrow: escrow,
            callback: msg.sender,
            projectId: projectId,
            kind: kind,
            milestone: milestone,
            round: round,
            end: end,
            eligible: eligible,
            yes: 0,
            no: 0,
            extension: rules.turnoutExtension,
            minTurnoutBps: rules.minTurnoutBps,
            approvalBps: rules.approvalBps,
            minVoteAmount: rules.minVoteAmount,
            fallbackApproves: rules.fallbackApproves,
            extended: false,
            closed: false,
            passed: false
        });
        emit VoteOpened(id, projectId, kind, milestone, round, end, eligible);
    }

    /// @param proofs The holder's leaves for this project, in strictly increasing leaf-hash
    /// order so none can be counted twice.
    function castVoteBySig(
        bytes32 id,
        address holder,
        bool approve,
        LeafProof[] calldata proofs,
        bytes calldata signature
    ) external {
        Ballot storage b = _ballots[id];
        if (b.escrow == address(0)) revert UnknownBallot(id);
        if (b.closed || block.timestamp >= b.end) revert VotingClosed(id);
        if (hasVoted[id][holder]) revert AlreadyVoted(holder);

        address signer = IReceiptToken(hub.receipts()).controllerOf(b.projectId, holder);
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.VOTE_TYPEHASH,
                b.projectId,
                holder,
                b.kind,
                b.milestone,
                b.round,
                approve
            )
        );
        Signatures.check(hub, signer, structHash, signature);

        uint256 weight = _eligibleAmount(b, holder, proofs);
        if (weight < b.minVoteAmount) revert BelowMinimum(weight, b.minVoteAmount);

        hasVoted[id][holder] = true;
        if (approve) b.yes++;
        else b.no++;
        emit VoteCast(id, holder, approve, uint64(weight));
    }

    /// @notice Closes a vote after its window. Low turnout extends the window once; if it is
    /// still too low the Passport's fallback decides a milestone vote, and an amendment or stop
    /// vote fails.
    function close(bytes32 id) external {
        Ballot storage b = _ballots[id];
        if (b.escrow == address(0)) revert UnknownBallot(id);
        if (b.closed) revert VotingClosed(id);
        if (block.timestamp < b.end) revert StillOpen(b.end);
        uint256 cast = uint256(b.yes) + b.no;
        uint256 eligible = cast > b.eligible ? cast : b.eligible;

        bool turnoutMet = cast > 0 && cast * 10_000 >= uint256(b.minTurnoutBps) * eligible;
        bool passed;
        if (turnoutMet) {
            passed = uint256(b.yes) * 10_000 > uint256(b.approvalBps) * cast;
        } else if (!b.extended && b.extension > 0 && eligible > 0) {
            b.extended = true;
            b.end += b.extension;
            emit VoteExtended(id, b.end);
            return;
        } else {
            passed = b.kind == VeritasTypes.BALLOT_MILESTONE && b.fallbackApproves;
        }

        b.closed = true;
        b.passed = passed;
        emit VoteClosed(id, passed, b.yes, b.no, !turnoutMet);
        IBallotCallback(b.callback)
            .onBallotClosed(b.projectId, b.kind, b.milestone, b.round, passed);
    }

    function _eligibleAmount(Ballot storage b, address holder, LeafProof[] calldata proofs)
        private
        view
        returns (uint256 total)
    {
        IDonationLedger ledger = IDonationLedger(hub.ledger());
        bytes32 previous;
        for (uint256 i = 0; i < proofs.length; i++) {
            LeafProof calldata p = proofs[i];
            if (p.leaf.holder != holder || p.leaf.projectId != b.projectId) revert WrongLeaf();
            if (b.kind == VeritasTypes.BALLOT_MILESTONE && p.leaf.milestone != b.milestone) {
                revert WrongLeaf();
            }
            bytes32 leafHash = ledger.verifyLeaf(p.batchId, p.leaf, p.proof);
            if (leafHash <= previous) revert DuplicateLeaf();
            previous = leafHash;
            total += p.leaf.amount;
        }
    }
}
