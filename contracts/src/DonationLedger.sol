// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import {Credit, DonationLeaf, VeritasTypes} from "./libraries/VeritasTypes.sol";
import {Signatures} from "./libraries/Signatures.sol";
import {IMilestoneEscrow, IVAZN, IVeritasHub} from "./interfaces/IVeritas.sol";

/// @title DonationLedger
/// @notice Hourly donation batches and the daily balance check.
/// @dev Bank mode: the bank signs each batch's root and per-milestone totals, the escrows are
/// credited and the matching vAZN is minted at once. Provider mode, when card money reaches
/// the escrow account a day or two later: the relayer anchors the root and totals as a Veritas
/// claim, the escrows record them, and vAZN is minted when the bank signs that the money has
/// settled. Proofs against a batch count only once it has settled.
///
/// The daily attestation compares the bank's escrow balance with the vAZN supply at the bank's
/// cut-off block. A mismatch, or no attestation for 36 hours, stops all releases until a
/// balanced one arrives.
contract DonationLedger {
    uint256 public constant MAX_ATTESTATION_AGE = 36 hours;

    struct Batch {
        bytes32 root;
        bytes32 creditsHash;
        uint64 total;
        uint32 leafCount;
        bool settled;
    }

    IVeritasHub public immutable hub;
    mapping(uint64 => Batch) public batches;
    uint64 public lastBatchId;

    uint64 public lastAttestedDay;
    uint64 public lastCutoffBlock;
    uint64 public lastCutoffTime;
    bool public lastBalanced;

    event BatchAnchored(
        uint64 indexed batchId,
        bytes32 root,
        uint32 leafCount,
        uint64 total,
        bytes32 creditsHash,
        bool settled
    );
    event BatchSettled(uint64 indexed batchId);
    event BalanceAttested(
        uint64 indexed day,
        uint64 cutoffBlock,
        uint64 cutoffTime,
        uint64 balance,
        uint256 supply,
        bool balanced,
        bytes32 statementHash
    );

    error WrongBatchId(uint64 expected, uint64 given);
    error EmptyBatch();
    error NotRelayer();
    error UnknownBatch(uint64 batchId);
    error AlreadySettled(uint64 batchId);
    error BatchNotSettled(uint64 batchId);
    error CreditsMismatch();
    error UnknownProject(bytes16 projectId);
    error AmountTooLarge();
    error BadProof();
    error StaleAttestation();
    error BadCutoff();

    constructor(IVeritasHub hub_) {
        hub = hub_;
    }

    /// @param bankSignature The bank's BatchAttestation, or empty for a Veritas-signed batch in
    /// provider mode, which only the relayer may send.
    function anchorBatch(
        uint64 batchId,
        bytes32 root,
        uint32 leafCount,
        Credit[] calldata credits,
        bytes calldata bankSignature
    ) external {
        if (batchId != lastBatchId + 1) {
            revert WrongBatchId(lastBatchId + 1, batchId);
        }
        if (root == bytes32(0) || leafCount == 0) revert EmptyBatch();
        uint64 total = _total(credits);
        bytes32 creditsHash = VeritasTypes.hashCredits(credits);
        bool settled = bankSignature.length > 0;
        if (settled) {
            bytes32 structHash = keccak256(
                abi.encode(
                    VeritasTypes.BATCH_ATTESTATION_TYPEHASH,
                    batchId,
                    root,
                    leafCount,
                    total,
                    creditsHash
                )
            );
            Signatures.check(hub, hub.bank(), structHash, bankSignature);
        } else if (msg.sender != hub.relayer()) {
            revert NotRelayer();
        }

        lastBatchId = batchId;
        batches[batchId] = Batch(root, creditsHash, total, leafCount, settled);
        emit BatchAnchored(batchId, root, leafCount, total, creditsHash, settled);

        IVAZN vazn = IVAZN(hub.vazn());
        for (uint256 i = 0; i < credits.length; i++) {
            address escrow = _escrow(credits[i].projectId);
            IMilestoneEscrow(escrow).credit(batchId, credits[i].amounts);
            if (settled) vazn.mint(escrow, _sum(credits[i].amounts));
        }
        if (settled) emit BatchSettled(batchId);
    }

    /// @notice The bank confirms that a provider-mode batch's money reached the escrow account.
    function settleBatch(uint64 batchId, Credit[] calldata credits, bytes calldata bankSignature)
        external
    {
        Batch storage batch = batches[batchId];
        if (batch.root == bytes32(0)) revert UnknownBatch(batchId);
        if (batch.settled) revert AlreadySettled(batchId);
        bytes32 creditsHash = VeritasTypes.hashCredits(credits);
        if (creditsHash != batch.creditsHash) revert CreditsMismatch();
        bytes32 structHash =
            keccak256(abi.encode(VeritasTypes.SETTLEMENT_TYPEHASH, batchId, creditsHash));
        Signatures.check(hub, hub.bank(), structHash, bankSignature);

        batch.settled = true;
        IVAZN vazn = IVAZN(hub.vazn());
        for (uint256 i = 0; i < credits.length; i++) {
            vazn.mint(_escrow(credits[i].projectId), _sum(credits[i].amounts));
        }
        emit BatchSettled(batchId);
    }

    /// @notice The bank's daily statement: its escrow balance at a cut-off block.
    function attestBalance(
        uint64 day,
        uint64 cutoffBlock,
        uint64 cutoffTime,
        uint64 balance,
        bytes32 statementHash,
        bytes calldata bankSignature
    ) external {
        if (day <= lastAttestedDay) revert StaleAttestation();
        if (cutoffBlock >= block.number || cutoffBlock < lastCutoffBlock) revert BadCutoff();
        if (cutoffTime > block.timestamp || cutoffTime < lastCutoffTime) revert BadCutoff();
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.BALANCE_ATTESTATION_TYPEHASH,
                day,
                cutoffBlock,
                cutoffTime,
                balance,
                statementHash
            )
        );
        Signatures.check(hub, hub.bank(), structHash, bankSignature);

        uint256 supply = IVAZN(hub.vazn()).totalSupplyAt(cutoffBlock);
        bool balanced = supply == balance;
        lastAttestedDay = day;
        lastCutoffBlock = cutoffBlock;
        lastCutoffTime = cutoffTime;
        lastBalanced = balanced;
        emit BalanceAttested(day, cutoffBlock, cutoffTime, balance, supply, balanced, statementHash);
    }

    /// @notice True while the last attestation balanced and is at most 36 hours old.
    function reconciled() external view returns (bool) {
        return lastBalanced && block.timestamp <= uint256(lastCutoffTime) + MAX_ATTESTATION_AGE;
    }

    /// @notice Reverts unless the leaf is in a settled batch. Used for votes, receipts and claims.
    function verifyLeaf(uint64 batchId, DonationLeaf calldata leaf, bytes32[] calldata proof)
        external
        view
        returns (bytes32 leafHash)
    {
        Batch storage batch = batches[batchId];
        if (!batch.settled) revert BatchNotSettled(batchId);
        leafHash = VeritasTypes.hashLeaf(leaf);
        if (!MerkleProof.verifyCalldata(proof, batch.root, leafHash)) revert BadProof();
    }

    /// @notice For receipts and the public verifier: is this leaf in the batch's root?
    function isInBatch(uint64 batchId, DonationLeaf calldata leaf, bytes32[] calldata proof)
        external
        view
        returns (bool)
    {
        bytes32 root = batches[batchId].root;
        return
            root != bytes32(0)
                && MerkleProof.verifyCalldata(proof, root, VeritasTypes.hashLeaf(leaf));
    }

    function _escrow(bytes16 projectId) private view returns (address escrow) {
        escrow = hub.escrowOf(projectId);
        if (escrow == address(0)) revert UnknownProject(projectId);
    }

    function _total(Credit[] calldata credits) private pure returns (uint64) {
        uint256 total;
        for (uint256 i = 0; i < credits.length; i++) {
            total += _sum(credits[i].amounts);
        }
        if (total > type(uint64).max) revert AmountTooLarge();
        return uint64(total);
    }

    function _sum(uint64[] calldata amounts) private pure returns (uint64) {
        uint256 sum;
        for (uint256 i = 0; i < amounts.length; i++) {
            sum += amounts[i];
        }
        if (sum > type(uint64).max) revert AmountTooLarge();
        return uint64(sum);
    }
}
