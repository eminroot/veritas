// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {DecisionRules, DonationLeaf} from "../libraries/VeritasTypes.sol";

interface IVeritasHub {
    function admin() external view returns (address);
    function relayer() external view returns (address);
    function bank() external view returns (address);
    function vazn() external view returns (address);
    function ledger() external view returns (address);
    function vault() external view returns (address);
    function voting() external view returns (address);
    function receipts() external view returns (address);
    function registry() external view returns (address);
    function factory() external view returns (address);
    function isCharity(address account) external view returns (bool);
    function isOfficer(address account) external view returns (bool);
    function isEscrow(address account) external view returns (bool);
    function escrowOf(bytes16 projectId) external view returns (address);
    function registerEscrow(bytes16 projectId, address escrow) external;
    function releasesAllowed() external view returns (bool);
    function hashTypedData(bytes32 structHash) external view returns (bytes32);
}

interface IVAZN {
    function mint(address to, uint256 amount) external;
    function burn(address from, uint256 amount) external;
    function transfer(address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function totalSupply() external view returns (uint256);
    function totalSupplyAt(uint256 blockNumber) external view returns (uint256);
}

interface IDonationLedger {
    function verifyLeaf(uint64 batchId, DonationLeaf calldata leaf, bytes32[] calldata proof)
        external
        view
        returns (bytes32 leafHash);
    function reconciled() external view returns (bool);
}

interface IPassportRegistry {
    function recordLaunch(
        bytes16 projectId,
        bytes32 passportHash,
        bytes32 contractorHash,
        string calldata cid
    ) external;
    function versionOf(bytes16 projectId) external view returns (uint32);
    function contractorHashOf(bytes16 projectId) external view returns (bytes32);
}

interface IReceiptToken {
    function controllerOf(bytes16 projectId, address holder) external view returns (address);
    function holderCount(bytes16 projectId) external view returns (uint32);
}

interface IVotingModule {
    function open(
        bytes16 projectId,
        uint8 kind,
        uint8 milestone,
        uint32 round,
        uint32 eligible,
        DecisionRules calldata rules
    ) external returns (bytes32 ballotId);
}

interface IBankPayoutVault {
    function instructPayout(
        bytes16 projectId,
        uint8 milestone,
        uint64 amount,
        bytes32 contractorHash,
        bytes32 invoiceHash
    ) external returns (uint64 instructionId);
    function instructRefund(bytes16 projectId, address holder, uint64 amount, bytes32 claimId)
        external
        returns (uint64 instructionId);
}

/// Whoever opened a ballot hears how it ended: the escrow, or the registry for amendments.
interface IBallotCallback {
    function onBallotClosed(
        bytes16 projectId,
        uint8 kind,
        uint8 milestone,
        uint32 round,
        bool passed
    ) external;
}

interface IMilestoneEscrow is IBallotCallback {
    function projectId() external view returns (bytes16);
    function category() external view returns (uint8);
    function charity() external view returns (address);
    function isActive() external view returns (bool);
    function rules() external view returns (DecisionRules memory);
    function credit(uint64 batchId, uint64[] calldata amounts) external;
    function onPayoutConfirmed(uint64 instructionId, uint8 milestone) external;
    function onPayoutFailed(
        uint64 instructionId,
        bool isRefund,
        uint8 milestone,
        address holder,
        uint64 amount
    ) external;
    function receiveRedirect(bytes16 fromProject, uint64 amount, bytes32 claimId) external;
}
