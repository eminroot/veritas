// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

/// @notice Formats shared by every Veritas contract and by the Python backend.
/// @dev Field order and types here are the protocol. `backend/src/veritas/chain/leaves.py` and
/// `backend/src/veritas/chain/eip712.py` build the same bytes, and test vectors made in Python
/// are checked against these definitions in `test/Vectors.t.sol`.

/// One donation's part for one milestone. Same fields and order as DONATION_LEAF_TYPES in Python.
struct DonationLeaf {
    bytes16 donationId;
    address holder;
    bytes16 projectId;
    uint8 milestone;
    uint64 amount;
    bytes32 trigger;
    bytes32 salt;
}

/// A leaf with the batch it was anchored in and its Merkle proof.
struct LeafProof {
    uint64 batchId;
    DonationLeaf leaf;
    bytes32[] proof;
}

/// Voting rules from the Passport's `decision` section, converted to seconds.
struct DecisionRules {
    uint32 voteWindow;
    uint32 turnoutExtension;
    uint16 minTurnoutBps;
    uint16 approvalBps;
    uint64 minVoteAmount;
    bool fallbackApproves;
}

/// Rules from the Passport's `stop` section, converted to seconds.
struct StopRules {
    uint32 evidenceGrace;
    uint32 choiceWindow;
    bool unclaimedRedirects;
}

/// Everything an escrow needs from the Passport. The charity signs its hash at launch.
struct ProjectConfig {
    bytes16 projectId;
    address charity;
    address officer;
    uint8 category;
    uint8 allocation;
    uint64[] budgets;
    uint64[] evidenceDeadlines;
    DecisionRules rules;
    StopRules stop;
    bytes32 contractorHash;
}

/// One project's share of an hourly batch, in qəpik per milestone.
struct Credit {
    bytes16 projectId;
    uint64[] amounts;
}

library VeritasTypes {
    uint8 internal constant ALLOCATION_PRO_RATA = 0;
    uint8 internal constant ALLOCATION_SEQUENTIAL = 1;
    uint8 internal constant CATEGORY_COUNT = 8;
    uint256 internal constant MAX_MILESTONES = 50;

    uint8 internal constant BALLOT_MILESTONE = 0;
    uint8 internal constant BALLOT_AMENDMENT = 1;
    uint8 internal constant BALLOT_STOP = 2;

    uint8 internal constant CHOICE_REFUND = 1;
    uint8 internal constant CHOICE_REDIRECT = 2;

    // EIP-712 types. Every message is signed in the one "Veritas" domain of the VeritasHub.
    bytes32 internal constant PROJECT_LAUNCH_TYPEHASH = keccak256(
        "ProjectLaunch(bytes16 projectId,uint32 version,bytes32 passportHash,string cid,bytes32 configHash)"
    );
    bytes32 internal constant EVIDENCE_TYPEHASH =
        keccak256("Evidence(bytes16 projectId,uint8 milestone,uint32 attempt,bytes32 bundleHash)");
    bytes32 internal constant DECISION_TYPEHASH = keccak256(
        "Decision(bytes16 projectId,uint8 milestone,uint32 attempt,bool approve,bytes32 bundleHash,bytes32 reportHash,bytes32 invoiceHash,uint64 amount,bool overrideChecks,bytes32 reasonHash)"
    );
    bytes32 internal constant VOTE_TYPEHASH = keccak256(
        "Vote(bytes16 projectId,address holder,uint8 kind,uint8 milestone,uint32 round,bool approve)"
    );
    bytes32 internal constant CHOICE_TYPEHASH = keccak256(
        "Choice(bytes16 projectId,address holder,uint8 action,address target,uint32 nonce,uint64 deadline)"
    );
    bytes32 internal constant WITHDRAW_TYPEHASH =
        keccak256("Withdraw(bytes16 projectId,bytes32 reasonHash)");
    bytes32 internal constant STOP_PROPOSAL_TYPEHASH =
        keccak256("StopProposal(bytes16 projectId,uint32 round,bytes32 reasonHash)");
    bytes32 internal constant AMENDMENT_TYPEHASH = keccak256(
        "Amendment(bytes16 projectId,uint32 version,bytes32 passportHash,string cid,bytes32 contractorHash)"
    );
    bytes32 internal constant COMPLETION_TYPEHASH =
        keccak256("Completion(bytes16 projectId,bytes32 reportHash,string cid)");
    bytes32 internal constant BATCH_ATTESTATION_TYPEHASH = keccak256(
        "BatchAttestation(uint64 batchId,bytes32 root,uint32 leafCount,uint64 total,bytes32 creditsHash)"
    );
    bytes32 internal constant SETTLEMENT_TYPEHASH =
        keccak256("Settlement(uint64 batchId,bytes32 creditsHash)");
    bytes32 internal constant BALANCE_ATTESTATION_TYPEHASH = keccak256(
        "BalanceAttestation(uint64 day,uint64 cutoffBlock,uint64 cutoffTime,uint64 balance,bytes32 statementHash)"
    );
    bytes32 internal constant PAYOUT_CONFIRMATION_TYPEHASH =
        keccak256("PayoutConfirmation(uint64 instructionId,uint64 amount,bytes32 paymentRef)");
    bytes32 internal constant PAYOUT_FAILURE_TYPEHASH =
        keccak256("PayoutFailure(uint64 instructionId,bytes32 reasonHash)");
    bytes32 internal constant KEY_ROTATION_TYPEHASH =
        keccak256("KeyRotation(uint256 receiptId,address newKey,uint64 nonce,uint64 deadline)");
    bytes32 internal constant ROTATION_CANCEL_TYPEHASH =
        keccak256("RotationCancel(uint256 receiptId,address newKey,uint64 readyAt)");

    /// keccak256(keccak256(abi.encode(fields))), the leaf hash of OpenZeppelin's StandardMerkleTree.
    function hashLeaf(DonationLeaf calldata leaf) internal pure returns (bytes32) {
        return keccak256(
            bytes.concat(
                keccak256(
                    abi.encode(
                        leaf.donationId,
                        leaf.holder,
                        leaf.projectId,
                        leaf.milestone,
                        leaf.amount,
                        leaf.trigger,
                        leaf.salt
                    )
                )
            )
        );
    }

    function hashConfig(ProjectConfig calldata config) internal pure returns (bytes32) {
        return keccak256(abi.encode(config));
    }

    function hashCredits(Credit[] calldata credits) internal pure returns (bytes32) {
        return keccak256(abi.encode(credits));
    }
}
