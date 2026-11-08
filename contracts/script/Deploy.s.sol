// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Script, console2} from "forge-std/Script.sol";
import {VeritasHub} from "../src/VeritasHub.sol";
import {VAZN} from "../src/VAZN.sol";
import {PassportRegistry} from "../src/PassportRegistry.sol";
import {DonationLedger} from "../src/DonationLedger.sol";
import {ReceiptToken} from "../src/ReceiptToken.sol";
import {VotingModule} from "../src/VotingModule.sol";
import {BankPayoutVault} from "../src/BankPayoutVault.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";
import {EscrowFactory} from "../src/EscrowFactory.sol";
import {IVeritasHub} from "../src/interfaces/IVeritas.sol";

/// @notice Deploys and wires the whole system, then writes the addresses to
/// deployments/<chain id>.json for the backend.
///
/// Anvil, with its default accounts as admin, relayer and bank:
///   forge script script/Deploy.s.sol --rpc-url http://127.0.0.1:8545 --broadcast \
///     --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
///
/// Polygon Amoy: set VERITAS_ADMIN (the Safe), VERITAS_RELAYER and VERITAS_BANK, then
///   forge script script/Deploy.s.sol --rpc-url $AMOY_RPC_URL --broadcast --account deployer
contract Deploy is Script {
    // Anvil's accounts 0, 1 and 2. Only used when the variables are not set.
    address internal constant ANVIL_ADMIN = 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266;
    address internal constant ANVIL_RELAYER = 0x70997970C51812dc3A010C7d01b50e0d17dc79C8;
    address internal constant ANVIL_BANK = 0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC;

    function run() external {
        address admin = vm.envOr("VERITAS_ADMIN", ANVIL_ADMIN);
        address relayer = vm.envOr("VERITAS_RELAYER", ANVIL_RELAYER);
        address bank = vm.envOr("VERITAS_BANK", ANVIL_BANK);
        if (block.chainid != 31_337) {
            require(vm.envExists("VERITAS_ADMIN"), "set VERITAS_ADMIN outside Anvil");
            require(vm.envExists("VERITAS_BANK"), "set VERITAS_BANK outside Anvil");
        }

        vm.startBroadcast();
        VeritasHub hub = new VeritasHub(admin, relayer, bank);
        IVeritasHub ihub = IVeritasHub(address(hub));
        VAZN vazn = new VAZN(ihub);
        PassportRegistry registry = new PassportRegistry(ihub);
        DonationLedger ledger = new DonationLedger(ihub);
        ReceiptToken receipts = new ReceiptToken(ihub);
        VotingModule voting = new VotingModule(ihub);
        BankPayoutVault vault = new BankPayoutVault(ihub);
        MilestoneEscrow implementation = new MilestoneEscrow(ihub);
        EscrowFactory factory = new EscrowFactory(ihub, address(implementation));
        hub.wire(
            address(vazn),
            address(ledger),
            address(vault),
            address(voting),
            address(receipts),
            address(registry),
            address(factory)
        );
        vm.stopBroadcast();

        string memory key = "deployment";
        vm.serializeUint(key, "chainId", block.chainid);
        vm.serializeUint(key, "startBlock", block.number);
        vm.serializeAddress(key, "VeritasHub", address(hub));
        vm.serializeAddress(key, "VAZN", address(vazn));
        vm.serializeAddress(key, "PassportRegistry", address(registry));
        vm.serializeAddress(key, "DonationLedger", address(ledger));
        vm.serializeAddress(key, "ReceiptToken", address(receipts));
        vm.serializeAddress(key, "VotingModule", address(voting));
        vm.serializeAddress(key, "BankPayoutVault", address(vault));
        vm.serializeAddress(key, "MilestoneEscrow", address(implementation));
        string memory json = vm.serializeAddress(key, "EscrowFactory", address(factory));
        string memory path =
            string.concat(vm.projectRoot(), "/deployments/", vm.toString(block.chainid), ".json");
        vm.writeJson(json, path);
        console2.log("Veritas deployed, addresses in", path);
    }
}
