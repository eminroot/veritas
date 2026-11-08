// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {IDonationLedger} from "./interfaces/IVeritas.sol";

/// @title VeritasHub
/// @notice Roles, wiring and the release pause, plus the one EIP-712 domain every Veritas
/// message is signed in.
/// @dev The admin (a Safe multisig in production) registers charities and officers and can
/// pause releases. It cannot move money or change a live project: escrows copy their rules at
/// launch, and vAZN can only be minted and burned by the ledger and the vault against bank
/// signatures. Changing the admin, relayer or bank key takes 48 hours and is public the whole
/// time. Revoking the relayer is immediate, for a leaked key.
contract VeritasHub is EIP712 {
    uint256 public constant KEY_CHANGE_DELAY = 48 hours;

    enum Role {
        Admin,
        Relayer,
        Bank
    }

    struct PendingKey {
        address key;
        uint64 readyAt;
    }

    address public admin;
    address public relayer;
    address public bank;
    mapping(Role => PendingKey) public pendingKey;

    address public immutable deployer;
    bool public wired;
    address public vazn;
    address public ledger;
    address public vault;
    address public voting;
    address public receipts;
    address public registry;
    address public factory;

    mapping(address => bool) public isCharity;
    mapping(address => bool) public isOfficer;
    mapping(address => bool) public isEscrow;
    mapping(bytes16 => address) public escrowOf;

    bool public releasesPaused;

    event Wired(
        address vazn,
        address ledger,
        address vault,
        address voting,
        address receipts,
        address registry,
        address factory
    );
    event CharitySet(address indexed charity, bool registered);
    event OfficerSet(address indexed officer, bool registered);
    event EscrowRegistered(bytes16 indexed projectId, address escrow);
    event ReleasesPaused(bool paused);
    event KeyChangeProposed(Role indexed role, address key, uint64 readyAt);
    event KeyChangeCancelled(Role indexed role);
    event KeyChanged(Role indexed role, address key);

    error NotAdmin();
    error NotDeployer();
    error AlreadyWired();
    error NotFactory();
    error ZeroAddress();
    error ProjectExists(bytes16 projectId);
    error NoPendingKey();
    error KeyNotReady(uint64 readyAt);

    modifier onlyAdmin() {
        if (msg.sender != admin) revert NotAdmin();
        _;
    }

    constructor(address admin_, address relayer_, address bank_) EIP712("Veritas", "1") {
        if (admin_ == address(0) || relayer_ == address(0) || bank_ == address(0)) {
            revert ZeroAddress();
        }
        admin = admin_;
        relayer = relayer_;
        bank = bank_;
        deployer = msg.sender;
    }

    /// @notice Connects the system contracts, once. After this nothing can rewire them.
    function wire(
        address vazn_,
        address ledger_,
        address vault_,
        address voting_,
        address receipts_,
        address registry_,
        address factory_
    ) external {
        if (msg.sender != deployer) revert NotDeployer();
        if (wired) revert AlreadyWired();
        if (
            vazn_ == address(0) || ledger_ == address(0) || vault_ == address(0)
                || voting_ == address(0) || receipts_ == address(0) || registry_ == address(0)
                || factory_ == address(0)
        ) revert ZeroAddress();
        wired = true;
        vazn = vazn_;
        ledger = ledger_;
        vault = vault_;
        voting = voting_;
        receipts = receipts_;
        registry = registry_;
        factory = factory_;
        emit Wired(vazn_, ledger_, vault_, voting_, receipts_, registry_, factory_);
    }

    function registerEscrow(bytes16 projectId, address escrow) external {
        if (msg.sender != factory) revert NotFactory();
        if (escrowOf[projectId] != address(0)) revert ProjectExists(projectId);
        escrowOf[projectId] = escrow;
        isEscrow[escrow] = true;
        emit EscrowRegistered(projectId, escrow);
    }

    function setCharity(address charity, bool registered) external onlyAdmin {
        if (charity == address(0)) revert ZeroAddress();
        isCharity[charity] = registered;
        emit CharitySet(charity, registered);
    }

    function setOfficer(address officer, bool registered) external onlyAdmin {
        if (officer == address(0)) revert ZeroAddress();
        isOfficer[officer] = registered;
        emit OfficerSet(officer, registered);
    }

    function setReleasesPaused(bool paused) external onlyAdmin {
        releasesPaused = paused;
        emit ReleasesPaused(paused);
    }

    function proposeKey(Role role, address key) external onlyAdmin {
        if (key == address(0)) revert ZeroAddress();
        uint64 readyAt = uint64(block.timestamp + KEY_CHANGE_DELAY);
        pendingKey[role] = PendingKey(key, readyAt);
        emit KeyChangeProposed(role, key, readyAt);
    }

    function cancelKey(Role role) external onlyAdmin {
        if (pendingKey[role].key == address(0)) revert NoPendingKey();
        delete pendingKey[role];
        emit KeyChangeCancelled(role);
    }

    /// @notice Anyone can apply a proposed key once its delay has passed.
    function applyKey(Role role) external {
        PendingKey memory pending = pendingKey[role];
        if (pending.key == address(0)) revert NoPendingKey();
        if (block.timestamp < pending.readyAt) revert KeyNotReady(pending.readyAt);
        delete pendingKey[role];
        if (role == Role.Admin) admin = pending.key;
        else if (role == Role.Relayer) relayer = pending.key;
        else bank = pending.key;
        emit KeyChanged(role, pending.key);
    }

    /// @notice Stops a leaked relayer key at once. Its Veritas claims stop until a new key applies.
    function revokeRelayer() external onlyAdmin {
        relayer = address(0);
        emit KeyChanged(Role.Relayer, address(0));
    }

    /// @notice Releases need an unpaused system and a fresh, balanced bank attestation.
    function releasesAllowed() external view returns (bool) {
        return !releasesPaused && ledger != address(0) && IDonationLedger(ledger).reconciled();
    }

    function hashTypedData(bytes32 structHash) external view returns (bytes32) {
        return _hashTypedDataV4(structHash);
    }

    function domainSeparator() external view returns (bytes32) {
        return _domainSeparatorV4();
    }
}
