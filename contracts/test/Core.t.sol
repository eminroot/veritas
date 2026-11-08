// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Base} from "./Base.t.sol";
import {VeritasHub} from "../src/VeritasHub.sol";
import {VAZN} from "../src/VAZN.sol";
import {EscrowFactory} from "../src/EscrowFactory.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";
import {PassportRegistry} from "../src/PassportRegistry.sol";
import {Signatures} from "../src/libraries/Signatures.sol";
import {ProjectConfig} from "../src/libraries/VeritasTypes.sol";
import {IVeritasHub} from "../src/interfaces/IVeritas.sol";

contract VAZNTest is Base {
    function test_twoDecimalsAndName() public view {
        assertEq(vazn.decimals(), 2);
        assertEq(vazn.symbol(), "vAZN");
    }

    function test_onlyLedgerMintsAndOnlyVaultBurns() public {
        MilestoneEscrow escrow = launchDefault(1);
        vm.expectRevert(VAZN.OnlyLedger.selector);
        vazn.mint(address(escrow), 100);
        vm.prank(address(ledger));
        vazn.mint(address(escrow), 100);
        vm.expectRevert(VAZN.OnlyVault.selector);
        vazn.burn(address(escrow), 100);
    }

    function test_cannotLeaveVeritasContracts() public {
        MilestoneEscrow escrow = launchDefault(1);
        vm.prank(address(ledger));
        vm.expectRevert(abi.encodeWithSelector(VAZN.NotVeritasContract.selector, address(this)));
        vazn.mint(address(this), 100);

        vm.prank(address(ledger));
        vazn.mint(address(escrow), 100);
        vm.prank(address(escrow));
        vm.expectRevert(abi.encodeWithSelector(VAZN.NotVeritasContract.selector, address(this)));
        vazn.transfer(address(this), 1);

        vm.prank(address(escrow));
        assertTrue(vazn.transfer(address(vault), 40));
        assertEq(vazn.balanceOf(address(vault)), 40);

        vm.expectRevert(VAZN.ApprovalsDisabled.selector);
        vazn.approve(address(this), 1);
    }

    function test_supplyIsCheckpointedPerBlock() public {
        MilestoneEscrow escrow = launchDefault(1);
        uint256 start = block.number;
        vm.prank(address(ledger));
        vazn.mint(address(escrow), 500);
        vm.roll(start + 5);
        vm.prank(address(ledger));
        vazn.mint(address(escrow), 250);
        vm.roll(start + 6);
        assertEq(vazn.totalSupplyAt(start - 1), 0);
        assertEq(vazn.totalSupplyAt(start), 500);
        assertEq(vazn.totalSupplyAt(start + 4), 500);
        assertEq(vazn.totalSupplyAt(start + 5), 750);
        vm.expectRevert(abi.encodeWithSelector(VAZN.FutureBlock.selector, start + 6));
        vazn.totalSupplyAt(start + 6);
    }
}

contract HubTest is Base {
    function test_wiresOnlyOnce() public {
        vm.expectRevert(VeritasHub.AlreadyWired.selector);
        hub.wire(address(1), address(1), address(1), address(1), address(1), address(1), address(1));
        VeritasHub fresh = new VeritasHub(admin, relayer, bank);
        vm.prank(admin);
        vm.expectRevert(VeritasHub.NotDeployer.selector);
        fresh.wire(
            address(1), address(1), address(1), address(1), address(1), address(1), address(1)
        );
    }

    function test_adminRegistersCharitiesAndOfficers() public {
        address someone = address(0x1234);
        vm.expectRevert(VeritasHub.NotAdmin.selector);
        hub.setCharity(someone, true);
        vm.prank(admin);
        hub.setCharity(someone, true);
        assertTrue(hub.isCharity(someone));
        vm.prank(admin);
        hub.setOfficer(someone, true);
        assertTrue(hub.isOfficer(someone));
    }

    function test_onlyFactoryRegistersEscrows() public {
        vm.expectRevert(VeritasHub.NotFactory.selector);
        hub.registerEscrow(bytes16(uint128(1)), address(this));
    }

    function test_keyChangesWait48Hours() public {
        address newBank = address(0xB0B);
        vm.prank(admin);
        hub.proposeKey(VeritasHub.Role.Bank, newBank);
        vm.expectRevert(
            abi.encodeWithSelector(
                VeritasHub.KeyNotReady.selector, uint64(block.timestamp + 48 hours)
            )
        );
        hub.applyKey(VeritasHub.Role.Bank);
        vm.warp(block.timestamp + 48 hours);
        hub.applyKey(VeritasHub.Role.Bank);
        assertEq(hub.bank(), newBank);
        vm.expectRevert(VeritasHub.NoPendingKey.selector);
        hub.applyKey(VeritasHub.Role.Bank);
    }

    function test_adminCanCancelAKeyChange() public {
        vm.startPrank(admin);
        hub.proposeKey(VeritasHub.Role.Admin, address(0xAD));
        hub.cancelKey(VeritasHub.Role.Admin);
        vm.stopPrank();
        vm.warp(block.timestamp + 3 days);
        vm.expectRevert(VeritasHub.NoPendingKey.selector);
        hub.applyKey(VeritasHub.Role.Admin);
        assertEq(hub.admin(), admin);
    }

    function test_relayerCanBeRevokedAtOnce() public {
        vm.prank(admin);
        hub.revokeRelayer();
        assertEq(hub.relayer(), address(0));
    }

    function test_releasesNeedFreshBalancedAttestationAndNoPause() public {
        assertFalse(hub.releasesAllowed());
        attestBalanced();
        assertTrue(hub.releasesAllowed());
        vm.prank(admin);
        hub.setReleasesPaused(true);
        assertFalse(hub.releasesAllowed());
        vm.prank(admin);
        hub.setReleasesPaused(false);
        assertTrue(hub.releasesAllowed());
        vm.warp(block.timestamp + 36 hours + 1);
        assertFalse(hub.releasesAllowed());
    }

    function test_domainSeparatorFollowsTheHub() public view {
        bytes32 expected = keccak256(
            abi.encode(
                keccak256(
                    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
                ),
                keccak256("Veritas"),
                keccak256("1"),
                block.chainid,
                address(hub)
            )
        );
        assertEq(hub.domainSeparator(), expected);
    }
}

contract FactoryTest is Base {
    function test_launchCreatesTheEscrowWhereItWasPredicted() public {
        ProjectConfig memory c = defaultConfig(projectIdOf(1));
        address predicted = factory.predictEscrow(c.projectId);
        MilestoneEscrow escrow = launch(c);
        assertEq(address(escrow), predicted);
        assertTrue(hub.isEscrow(predicted));
        assertEq(hub.escrowOf(c.projectId), predicted);
        assertEq(escrow.projectId(), c.projectId);
        assertEq(escrow.charity(), charity);
        assertEq(escrow.officer(), officer);
        assertEq(escrow.milestoneCount(), 3);
        assertEq(escrow.milestone(1).budget, 1_383_000);
        assertEq(escrow.rules().minVoteAmount, 500);

        PassportRegistry.Entry memory entry = registry.current(c.projectId);
        assertEq(entry.version, 1);
        assertEq(entry.passportHash, PASSPORT_HASH);
        assertEq(entry.contractorHash, CONTRACTOR);
        assertEq(entry.cid, CID);
    }

    function test_launchNeedsTheCharitysSignatureOverTheExactConfig() public {
        ProjectConfig memory c = defaultConfig(projectIdOf(1));
        bytes memory signature = launchSignature(c, PASSPORT_HASH, CID);
        c.budgets[0] += 1; // the config no longer matches what the charity signed
        vm.expectRevert(abi.encodeWithSelector(Signatures.BadSignature.selector, charity));
        factory.createProject(c, PASSPORT_HASH, CID, signature);
    }

    function test_launchNeedsRegisteredCharityAndOfficer() public {
        ProjectConfig memory c = defaultConfig(projectIdOf(1));
        c.officer = address(0x0FF);
        bytes memory signature = launchSignature(c, PASSPORT_HASH, CID);
        vm.expectRevert(abi.encodeWithSelector(EscrowFactory.NotOfficer.selector, address(0x0FF)));
        factory.createProject(c, PASSPORT_HASH, CID, signature);
        c = defaultConfig(projectIdOf(1));
        signature = launchSignature(c, PASSPORT_HASH, CID);
        vm.prank(admin);
        hub.setCharity(charity, false);
        vm.expectRevert(abi.encodeWithSelector(EscrowFactory.NotCharity.selector, charity));
        factory.createProject(c, PASSPORT_HASH, CID, signature);
    }

    function test_aProjectLaunchesOnce() public {
        launchDefault(1);
        ProjectConfig memory c = defaultConfig(projectIdOf(1));
        bytes memory signature = launchSignature(c, PASSPORT_HASH, CID);
        vm.expectRevert(); // the clone address is taken
        factory.createProject(c, PASSPORT_HASH, CID, signature);
    }

    function test_rejectsUnsafeConfigs() public {
        string[8] memory reasons = [
            "milestones",
            "deadlines",
            "category",
            "budget",
            "deadline passed",
            "vote window",
            "approval",
            "choice window"
        ];
        for (uint256 i = 0; i < reasons.length; i++) {
            ProjectConfig memory c = defaultConfig(projectIdOf(10 + i));
            if (i == 0) c.budgets = new uint64[](0);
            if (i == 0) c.evidenceDeadlines = new uint64[](0);
            if (i == 1) c.evidenceDeadlines = new uint64[](2);
            if (i == 2) c.category = 8;
            if (i == 3) c.budgets[1] = 0;
            if (i == 4) c.evidenceDeadlines[2] = uint64(block.timestamp);
            if (i == 5) c.rules.voteWindow = 10 minutes;
            if (i == 6) c.rules.approvalBps = 4999;
            if (i == 7) c.stop.choiceWindow = 1 hours;
            bytes memory signature = launchSignature(c, PASSPORT_HASH, CID);
            vm.expectRevert(abi.encodeWithSelector(EscrowFactory.BadConfig.selector, reasons[i]));
            factory.createProject(c, PASSPORT_HASH, CID, signature);
        }
    }

    function test_newImplementationOnlyForNewProjects() public {
        MilestoneEscrow first = launchDefault(1);
        MilestoneEscrow replacement = new MilestoneEscrow(IVeritasHub(address(hub)));
        vm.expectRevert(EscrowFactory.NotAdmin.selector);
        factory.setImplementation(address(replacement));
        vm.prank(admin);
        factory.setImplementation(address(replacement));
        MilestoneEscrow second = launchDefault(2);
        assertEq(first.projectId(), projectIdOf(1));
        assertEq(second.projectId(), projectIdOf(2));
        assertEq(factory.predictEscrow(projectIdOf(2)), address(second));
    }

    function test_cloneCannotBeInitialisedAgain() public {
        MilestoneEscrow escrow = launchDefault(1);
        ProjectConfig memory c = defaultConfig(projectIdOf(1));
        vm.expectRevert();
        escrow.initialize(c);
        vm.expectRevert();
        implementation.initialize(c);
    }
}
