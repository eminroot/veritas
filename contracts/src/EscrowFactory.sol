// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {ProjectConfig, VeritasTypes} from "./libraries/VeritasTypes.sol";
import {Signatures} from "./libraries/Signatures.sol";
import {IPassportRegistry, IVeritasHub} from "./interfaces/IVeritas.sol";
import {MilestoneEscrow} from "./MilestoneEscrow.sol";

/// @title EscrowFactory
/// @notice Launches a project: one MilestoneEscrow clone with the Passport's rules, and the
/// Passport's hash recorded in the registry.
/// @dev The charity signs a ProjectLaunch message over the Passport hash, where to fetch it,
/// and the hash of the on-chain config derived from it, so the rules the escrow enforces are
/// the ones the charity published. Anyone may submit it. The admin can point the factory at a
/// new implementation, which only applies to projects created afterwards.
contract EscrowFactory {
    IVeritasHub public immutable hub;
    address public implementation;

    event ProjectCreated(
        bytes16 indexed projectId,
        address escrow,
        bytes32 passportHash,
        bytes32 configHash,
        string cid
    );
    event ImplementationChanged(address implementation);

    error NotAdmin();
    error NotCharity(address charity);
    error NotOfficer(address officer);
    error BadConfig(string reason);

    constructor(IVeritasHub hub_, address implementation_) {
        if (implementation_ == address(0)) revert BadConfig("implementation");
        hub = hub_;
        implementation = implementation_;
        emit ImplementationChanged(implementation_);
    }

    function setImplementation(address implementation_) external {
        if (msg.sender != hub.admin()) revert NotAdmin();
        if (implementation_ == address(0)) revert BadConfig("implementation");
        implementation = implementation_;
        emit ImplementationChanged(implementation_);
    }

    /// @notice Where a project's escrow will live, known before it launches.
    function predictEscrow(bytes16 projectId) external view returns (address) {
        return Clones.predictDeterministicAddress(implementation, bytes32(projectId));
    }

    function createProject(
        ProjectConfig calldata config,
        bytes32 passportHash,
        string calldata cid,
        bytes calldata charitySignature
    ) external returns (address escrow) {
        if (!hub.isCharity(config.charity)) revert NotCharity(config.charity);
        if (!hub.isOfficer(config.officer)) revert NotOfficer(config.officer);
        _validate(config);
        if (passportHash == bytes32(0)) revert BadConfig("passport hash");

        bytes32 configHash = VeritasTypes.hashConfig(config);
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.PROJECT_LAUNCH_TYPEHASH,
                config.projectId,
                uint32(1),
                passportHash,
                keccak256(bytes(cid)),
                configHash
            )
        );
        Signatures.check(hub, config.charity, structHash, charitySignature);

        escrow = Clones.cloneDeterministic(implementation, bytes32(config.projectId));
        MilestoneEscrow(escrow).initialize(config);
        hub.registerEscrow(config.projectId, escrow);
        IPassportRegistry(hub.registry())
            .recordLaunch(config.projectId, passportHash, config.contractorHash, cid);
        emit ProjectCreated(config.projectId, escrow, passportHash, configHash, cid);
    }

    /// The Passport model in Python checks the same things more thoroughly. These are the rules
    /// the contracts rely on to stay safe.
    function _validate(ProjectConfig calldata c) private view {
        uint256 count = c.budgets.length;
        if (c.projectId == bytes16(0)) revert BadConfig("project id");
        if (count == 0 || count > VeritasTypes.MAX_MILESTONES) revert BadConfig("milestones");
        if (c.evidenceDeadlines.length != count) revert BadConfig("deadlines");
        if (c.category >= VeritasTypes.CATEGORY_COUNT) revert BadConfig("category");
        if (c.allocation > VeritasTypes.ALLOCATION_SEQUENTIAL) revert BadConfig("allocation");
        if (c.contractorHash == bytes32(0)) revert BadConfig("contractor");
        for (uint256 i = 0; i < count; i++) {
            if (c.budgets[i] == 0) revert BadConfig("budget");
            if (c.evidenceDeadlines[i] <= block.timestamp) revert BadConfig("deadline passed");
        }
        if (c.rules.voteWindow < 1 hours || c.rules.voteWindow > 30 days) {
            revert BadConfig("vote window");
        }
        if (c.rules.turnoutExtension > 30 days) revert BadConfig("extension");
        if (c.rules.minTurnoutBps > 10_000) revert BadConfig("turnout");
        if (c.rules.approvalBps < 5000 || c.rules.approvalBps >= 10_000) {
            revert BadConfig("approval");
        }
        if (c.rules.minVoteAmount == 0) revert BadConfig("minimum vote");
        if (c.stop.choiceWindow < 1 days || c.stop.choiceWindow > 365 days) {
            revert BadConfig("choice window");
        }
        if (c.stop.evidenceGrace > 365 days) revert BadConfig("grace");
    }
}
