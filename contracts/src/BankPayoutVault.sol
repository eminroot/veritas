// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {VeritasTypes} from "./libraries/VeritasTypes.sol";
import {Signatures} from "./libraries/Signatures.sol";
import {IMilestoneEscrow, IVAZN, IVeritasHub} from "./interfaces/IVeritas.sol";

/// @title BankPayoutVault
/// @notice Holds released vAZN until the bank says what happened to the manat.
/// @dev An escrow sends vAZN here and records an instruction: pay the contractor named in the
/// Passport against an invoice, or refund a donor. The bank acts on the event, then signs a
/// confirmation with its payment reference, which burns the vAZN, or a failure, which sends
/// the vAZN back to the escrow. Nobody else can settle an instruction.
contract BankPayoutVault {
    enum Status {
        None,
        Pending,
        Confirmed,
        Failed
    }

    struct Instruction {
        address escrow;
        bytes16 projectId;
        bool isRefund;
        uint8 milestone;
        uint64 amount;
        Status status;
        address holder;
        bytes32 contractorHash;
        bytes32 invoiceHash;
        bytes32 claimId;
    }

    IVeritasHub public immutable hub;
    mapping(uint64 => Instruction) private _instructions;
    uint64 public lastInstructionId;

    event ReleaseInstructed(
        uint64 indexed instructionId,
        bytes16 indexed projectId,
        uint8 milestone,
        uint64 amount,
        bytes32 contractorHash,
        bytes32 invoiceHash
    );
    event RefundInstructed(
        uint64 indexed instructionId,
        bytes16 indexed projectId,
        address holder,
        uint64 amount,
        bytes32 claimId
    );
    event PayoutConfirmed(uint64 indexed instructionId, bytes32 paymentRef);
    event PayoutFailed(uint64 indexed instructionId, bytes32 reasonHash);

    error NotEscrow();
    error NotPending(uint64 instructionId);
    error ZeroAmount();

    constructor(IVeritasHub hub_) {
        hub = hub_;
    }

    function instruction(uint64 id) external view returns (Instruction memory) {
        return _instructions[id];
    }

    /// @notice Called by an escrow right after it sent `amount` vAZN here.
    function instructPayout(
        bytes16 projectId,
        uint8 milestone,
        uint64 amount,
        bytes32 contractorHash,
        bytes32 invoiceHash
    ) external returns (uint64 id) {
        if (!hub.isEscrow(msg.sender)) revert NotEscrow();
        if (amount == 0) revert ZeroAmount();
        id = ++lastInstructionId;
        _instructions[id] = Instruction({
            escrow: msg.sender,
            projectId: projectId,
            isRefund: false,
            milestone: milestone,
            amount: amount,
            status: Status.Pending,
            holder: address(0),
            contractorHash: contractorHash,
            invoiceHash: invoiceHash,
            claimId: bytes32(0)
        });
        emit ReleaseInstructed(id, projectId, milestone, amount, contractorHash, invoiceHash);
    }

    function instructRefund(bytes16 projectId, address holder, uint64 amount, bytes32 claimId)
        external
        returns (uint64 id)
    {
        if (!hub.isEscrow(msg.sender)) revert NotEscrow();
        if (amount == 0) revert ZeroAmount();
        id = ++lastInstructionId;
        _instructions[id] = Instruction({
            escrow: msg.sender,
            projectId: projectId,
            isRefund: true,
            milestone: 0,
            amount: amount,
            status: Status.Pending,
            holder: holder,
            contractorHash: bytes32(0),
            invoiceHash: bytes32(0),
            claimId: claimId
        });
        emit RefundInstructed(id, projectId, holder, amount, claimId);
    }

    /// @notice The bank paid: burn the vAZN that stood for that manat.
    function confirm(uint64 id, bytes32 paymentRef, bytes calldata bankSignature) external {
        Instruction storage ins = _pending(id);
        bytes32 structHash = keccak256(
            abi.encode(VeritasTypes.PAYOUT_CONFIRMATION_TYPEHASH, id, ins.amount, paymentRef)
        );
        Signatures.check(hub, hub.bank(), structHash, bankSignature);
        ins.status = Status.Confirmed;
        IVAZN(hub.vazn()).burn(address(this), ins.amount);
        emit PayoutConfirmed(id, paymentRef);
        if (!ins.isRefund) IMilestoneEscrow(ins.escrow).onPayoutConfirmed(id, ins.milestone);
    }

    /// @notice The bank could not pay, for example a closed account or an expired card. The
    /// vAZN goes back to the escrow, which can try again.
    function fail(uint64 id, bytes32 reasonHash, bytes calldata bankSignature) external {
        Instruction storage ins = _pending(id);
        bytes32 structHash =
            keccak256(abi.encode(VeritasTypes.PAYOUT_FAILURE_TYPEHASH, id, reasonHash));
        Signatures.check(hub, hub.bank(), structHash, bankSignature);
        ins.status = Status.Failed;
        IVAZN(hub.vazn()).transfer(ins.escrow, ins.amount);
        emit PayoutFailed(id, reasonHash);
        IMilestoneEscrow(ins.escrow)
            .onPayoutFailed(id, ins.isRefund, ins.milestone, ins.holder, ins.amount);
    }

    function _pending(uint64 id) private view returns (Instruction storage ins) {
        ins = _instructions[id];
        if (ins.status != Status.Pending) revert NotPending(id);
    }
}
