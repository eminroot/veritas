// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {VeritasTypes} from "./libraries/VeritasTypes.sol";
import {Signatures} from "./libraries/Signatures.sol";
import {IMilestoneEscrow, IVeritasHub, IVotingModule} from "./interfaces/IVeritas.sol";

/// @title PassportRegistry
/// @notice The public index of Project Passports, and the only way to change one.
/// @dev Each entry is the SHA-256 of the published canonical bytes, where to fetch them, the
/// version, and the hash of the contractor the escrow may pay. Version 1 is written by the
/// factory at launch. A later version starts as the charity's signed amendment, goes to a
/// donor vote, and is recorded only if the vote passes while the project is still running.
/// An amendment can change the documents and the contractor, never the amounts or the rules,
/// which the escrow copied at launch.
contract PassportRegistry {
    struct Entry {
        uint32 version;
        bytes32 passportHash;
        bytes32 contractorHash;
        string cid;
    }

    struct Amendment {
        uint32 round;
        bool voteOpen;
        uint32 version;
        bytes32 passportHash;
        bytes32 contractorHash;
        string cid;
    }

    IVeritasHub public immutable hub;
    mapping(bytes16 => Entry) private _entries;
    mapping(bytes16 => Amendment) private _amendments;
    mapping(bytes16 => uint32) public amendmentRound;

    event PassportRecorded(
        bytes16 indexed projectId,
        uint32 version,
        bytes32 passportHash,
        bytes32 contractorHash,
        string cid
    );
    event AmendmentProposed(
        bytes16 indexed projectId,
        uint32 round,
        uint32 version,
        bytes32 passportHash,
        bytes32 contractorHash,
        string cid
    );
    event AmendmentRejected(bytes16 indexed projectId, uint32 round);

    error NotFactory();
    error NotRelayer();
    error NotVoting();
    error AlreadyLaunched(bytes16 projectId);
    error EmptyHash();
    error UnknownProject(bytes16 projectId);
    error ProjectNotActive(bytes16 projectId);
    error WrongVersion(uint32 expected, uint32 given);
    error AmendmentInProgress(bytes16 projectId);
    error NoAmendment(bytes16 projectId);

    constructor(IVeritasHub hub_) {
        hub = hub_;
    }

    function recordLaunch(
        bytes16 projectId,
        bytes32 passportHash,
        bytes32 contractorHash,
        string calldata cid
    ) external {
        if (msg.sender != hub.factory()) revert NotFactory();
        if (_entries[projectId].version != 0) revert AlreadyLaunched(projectId);
        _record(projectId, 1, passportHash, contractorHash, cid);
    }

    /// @notice The charity's signed proposal for the next Passport version.
    function proposeAmendment(
        bytes16 projectId,
        uint32 version,
        bytes32 passportHash,
        string calldata cid,
        bytes32 contractorHash,
        bytes calldata charitySignature
    ) external {
        IMilestoneEscrow escrow = _activeEscrow(projectId);
        Amendment storage pending = _amendments[projectId];
        if (pending.version != 0) revert AmendmentInProgress(projectId);
        uint32 expected = _entries[projectId].version + 1;
        if (version != expected) revert WrongVersion(expected, version);
        if (passportHash == bytes32(0) || contractorHash == bytes32(0)) revert EmptyHash();
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.AMENDMENT_TYPEHASH,
                projectId,
                version,
                passportHash,
                keccak256(bytes(cid)),
                contractorHash
            )
        );
        Signatures.check(hub, escrow.charity(), structHash, charitySignature);
        uint32 round = ++amendmentRound[projectId];
        _amendments[projectId] = Amendment(round, false, version, passportHash, contractorHash, cid);
        emit AmendmentProposed(projectId, round, version, passportHash, contractorHash, cid);
    }

    /// @notice Opens the donor vote on a proposed amendment, with Veritas's count of donors.
    function openAmendmentVote(bytes16 projectId, uint32 eligible) external {
        if (msg.sender != hub.relayer()) revert NotRelayer();
        IMilestoneEscrow escrow = _activeEscrow(projectId);
        Amendment storage pending = _amendments[projectId];
        if (pending.version == 0 || pending.voteOpen) revert NoAmendment(projectId);
        pending.voteOpen = true;
        IVotingModule(hub.voting())
            .open(
                projectId, VeritasTypes.BALLOT_AMENDMENT, 0, pending.round, eligible, escrow.rules()
            );
    }

    function onBallotClosed(bytes16 projectId, uint8, uint8, uint32 round, bool passed) external {
        if (msg.sender != hub.voting()) revert NotVoting();
        Amendment memory pending = _amendments[projectId];
        if (pending.round != round || !pending.voteOpen) return;
        delete _amendments[projectId];
        address escrow = hub.escrowOf(projectId);
        if (passed && IMilestoneEscrow(escrow).isActive()) {
            _record(
                projectId,
                pending.version,
                pending.passportHash,
                pending.contractorHash,
                pending.cid
            );
        } else {
            emit AmendmentRejected(projectId, round);
        }
    }

    function current(bytes16 projectId) external view returns (Entry memory) {
        return _entries[projectId];
    }

    function pendingAmendment(bytes16 projectId) external view returns (Amendment memory) {
        return _amendments[projectId];
    }

    function versionOf(bytes16 projectId) external view returns (uint32) {
        return _entries[projectId].version;
    }

    function contractorHashOf(bytes16 projectId) external view returns (bytes32) {
        return _entries[projectId].contractorHash;
    }

    function _activeEscrow(bytes16 projectId) private view returns (IMilestoneEscrow escrow) {
        address account = hub.escrowOf(projectId);
        if (account == address(0)) revert UnknownProject(projectId);
        escrow = IMilestoneEscrow(account);
        if (!escrow.isActive()) revert ProjectNotActive(projectId);
    }

    function _record(
        bytes16 projectId,
        uint32 version,
        bytes32 passportHash,
        bytes32 contractorHash,
        string memory cid
    ) private {
        if (passportHash == bytes32(0) || contractorHash == bytes32(0)) {
            revert EmptyHash();
        }
        Entry storage entry = _entries[projectId];
        entry.version = version;
        entry.passportHash = passportHash;
        entry.contractorHash = contractorHash;
        entry.cid = cid;
        emit PassportRecorded(projectId, version, passportHash, contractorHash, cid);
    }
}
