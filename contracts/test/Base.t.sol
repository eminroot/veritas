// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {VeritasHub} from "../src/VeritasHub.sol";
import {VAZN} from "../src/VAZN.sol";
import {PassportRegistry} from "../src/PassportRegistry.sol";
import {DonationLedger} from "../src/DonationLedger.sol";
import {ReceiptToken} from "../src/ReceiptToken.sol";
import {VotingModule} from "../src/VotingModule.sol";
import {BankPayoutVault} from "../src/BankPayoutVault.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";
import {EscrowFactory} from "../src/EscrowFactory.sol";
import {
    Credit,
    DecisionRules,
    DonationLeaf,
    LeafProof,
    ProjectConfig,
    StopRules,
    VeritasTypes
} from "../src/libraries/VeritasTypes.sol";
import {IVeritasHub} from "../src/interfaces/IVeritas.sol";

/// @notice Deploys the whole system and offers helpers to drive a project through its life.
abstract contract Base is Test {
    uint256 internal constant T0 = 1_800_000_000; // 2027-01-15, before the example deadlines

    uint256 internal constant ADMIN_PK = 0xA11CE;
    uint256 internal constant RELAYER_PK = 0x5E1A7;
    uint256 internal constant BANK_PK = 0xBA4C;
    uint256 internal constant CHARITY_PK = 0xC4A1;
    uint256 internal constant OFFICER_PK = 0x0FF1CE;

    address internal admin = vm.addr(ADMIN_PK);
    address internal relayer = vm.addr(RELAYER_PK);
    address internal bank = vm.addr(BANK_PK);
    address internal charity = vm.addr(CHARITY_PK);
    address internal officer = vm.addr(OFFICER_PK);

    VeritasHub internal hub;
    VAZN internal vazn;
    PassportRegistry internal registry;
    DonationLedger internal ledger;
    ReceiptToken internal receipts;
    VotingModule internal voting;
    BankPayoutVault internal vault;
    MilestoneEscrow internal implementation;
    EscrowFactory internal factory;

    uint64 internal attestationDay;
    uint256 internal leafNonce;
    string internal constant CID = "bafkreihdwdcefgh4dqkjv67uzcmw7ojee6xedzdetojuzjevtenxquvyku";
    bytes32 internal constant PASSPORT_HASH = keccak256("passport v1");
    bytes32 internal constant CONTRACTOR = keccak256("veritas:contractor:1300000021");

    function setUp() public virtual {
        vm.warp(T0);
        vm.roll(1000);
        deploySystem();
    }

    function deploySystem() internal {
        if (address(hub) == address(0)) hub = new VeritasHub(admin, relayer, bank);
        IVeritasHub ihub = IVeritasHub(address(hub));
        vazn = new VAZN(ihub);
        registry = new PassportRegistry(ihub);
        ledger = new DonationLedger(ihub);
        receipts = new ReceiptToken(ihub);
        voting = new VotingModule(ihub);
        vault = new BankPayoutVault(ihub);
        implementation = new MilestoneEscrow(ihub);
        factory = new EscrowFactory(ihub, address(implementation));
        hub.wire(
            address(vazn),
            address(ledger),
            address(vault),
            address(voting),
            address(receipts),
            address(registry),
            address(factory)
        );
        vm.startPrank(admin);
        hub.setCharity(charity, true);
        hub.setOfficer(officer, true);
        vm.stopPrank();
    }

    // ------------------------------------------------------------------ signing

    function sign(uint256 pk, bytes32 structHash) internal view returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, hub.hashTypedData(structHash));
        return abi.encodePacked(r, s, v);
    }

    // ------------------------------------------------------------------ projects

    function projectIdOf(uint256 n) internal pure returns (bytes16) {
        return bytes16(uint128(0x6f1c2a9e3b7d4e2a9c418d5b2f000000) + uint128(n));
    }

    function defaultConfig(bytes16 projectId) internal view returns (ProjectConfig memory c) {
        uint64[] memory budgets = new uint64[](3);
        budgets[0] = 420_000;
        budgets[1] = 1_383_000;
        budgets[2] = 246_000;
        uint64[] memory deadlines = new uint64[](3);
        deadlines[0] = uint64(block.timestamp + 60 days);
        deadlines[1] = uint64(block.timestamp + 120 days);
        deadlines[2] = uint64(block.timestamp + 180 days);
        c = ProjectConfig({
            projectId: projectId,
            charity: charity,
            officer: officer,
            category: 0,
            allocation: VeritasTypes.ALLOCATION_PRO_RATA,
            budgets: budgets,
            evidenceDeadlines: deadlines,
            rules: DecisionRules({
                voteWindow: 72 hours,
                turnoutExtension: 48 hours,
                minTurnoutBps: 1000,
                approvalBps: 5000,
                minVoteAmount: 500,
                fallbackApproves: true
            }),
            stop: StopRules({
                evidenceGrace: 14 days, choiceWindow: 30 days, unclaimedRedirects: false
            }),
            contractorHash: CONTRACTOR
        });
    }

    function launchSignature(ProjectConfig memory c, bytes32 passportHash, string memory cid)
        internal
        view
        returns (bytes memory)
    {
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.PROJECT_LAUNCH_TYPEHASH,
                c.projectId,
                uint32(1),
                passportHash,
                keccak256(bytes(cid)),
                keccak256(abi.encode(c))
            )
        );
        return sign(CHARITY_PK, structHash);
    }

    function launch(ProjectConfig memory c) internal returns (MilestoneEscrow) {
        bytes memory signature = launchSignature(c, PASSPORT_HASH, CID);
        return MilestoneEscrow(factory.createProject(c, PASSPORT_HASH, CID, signature));
    }

    function launchDefault(uint256 n) internal returns (MilestoneEscrow) {
        return launch(defaultConfig(projectIdOf(n)));
    }

    // ------------------------------------------------------------------ donations

    function donorKey(uint256 n) internal pure returns (uint256) {
        return 0xD0D0 + n;
    }

    function donor(uint256 n) internal pure returns (address) {
        return vm.addr(donorKey(n));
    }

    function makeLeaf(bytes16 projectId, address holder, uint8 milestone, uint64 amount)
        internal
        returns (DonationLeaf memory)
    {
        leafNonce++;
        return DonationLeaf({
            donationId: bytes16(uint128(leafNonce)),
            holder: holder,
            projectId: projectId,
            milestone: milestone,
            amount: amount,
            trigger: bytes32(0),
            salt: keccak256(abi.encode("salt", leafNonce))
        });
    }

    function hashLeaf(DonationLeaf memory l) internal pure returns (bytes32) {
        return keccak256(
            bytes.concat(
                keccak256(
                    abi.encode(
                        l.donationId,
                        l.holder,
                        l.projectId,
                        l.milestone,
                        l.amount,
                        l.trigger,
                        l.salt
                    )
                )
            )
        );
    }

    /// Credits for the leaves, one entry per project in order of first appearance.
    /// Leaves with a non-zero trigger byte 0x52 ("R") are redirect leaves and credit nothing.
    function creditsFor(DonationLeaf[] memory leaves) internal pure returns (Credit[] memory) {
        bytes16[] memory projects = new bytes16[](leaves.length);
        uint256 count;
        for (uint256 i = 0; i < leaves.length; i++) {
            bool seen;
            for (uint256 j = 0; j < count; j++) {
                if (projects[j] == leaves[i].projectId) seen = true;
            }
            if (!seen) projects[count++] = leaves[i].projectId;
        }
        Credit[] memory credits = new Credit[](count);
        for (uint256 j = 0; j < count; j++) {
            uint64[] memory amounts = new uint64[](3);
            for (uint256 i = 0; i < leaves.length; i++) {
                if (leaves[i].projectId == projects[j] && !isRedirectLeaf(leaves[i])) {
                    amounts[leaves[i].milestone] += leaves[i].amount;
                }
            }
            credits[j] = Credit(projects[j], amounts);
        }
        return credits;
    }

    function isRedirectLeaf(DonationLeaf memory l) internal pure returns (bool) {
        return l.trigger[0] == 0x52;
    }

    function totalOf(Credit[] memory credits) internal pure returns (uint64 total) {
        for (uint256 i = 0; i < credits.length; i++) {
            for (uint256 j = 0; j < credits[i].amounts.length; j++) {
                total += credits[i].amounts[j];
            }
        }
    }

    function bankBatchSignature(
        uint64 batchId,
        bytes32 root,
        uint32 leafCount,
        Credit[] memory credits
    ) internal view returns (bytes memory) {
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.BATCH_ATTESTATION_TYPEHASH,
                batchId,
                root,
                leafCount,
                totalOf(credits),
                keccak256(abi.encode(credits))
            )
        );
        return sign(BANK_PK, structHash);
    }

    /// Anchors the leaves as one bank-signed batch and returns a proof for each of them.
    function anchor(DonationLeaf[] memory leaves) internal returns (LeafProof[] memory proofs) {
        (bytes32 root, bytes32[][] memory paths) = merkle(leaves);
        uint64 batchId = ledger.lastBatchId() + 1;
        Credit[] memory credits = creditsFor(leaves);
        bytes memory signature = bankBatchSignature(batchId, root, uint32(leaves.length), credits);
        ledger.anchorBatch(batchId, root, uint32(leaves.length), credits, signature);
        proofs = new LeafProof[](leaves.length);
        for (uint256 i = 0; i < leaves.length; i++) {
            proofs[i] = LeafProof(batchId, leaves[i], paths[i]);
        }
    }

    function anchorOne(DonationLeaf memory l) internal returns (LeafProof memory) {
        DonationLeaf[] memory leaves = new DonationLeaf[](1);
        leaves[0] = l;
        return anchor(leaves)[0];
    }

    function one(LeafProof memory p) internal pure returns (LeafProof[] memory list) {
        list = new LeafProof[](1);
        list[0] = p;
    }

    /// The bank's daily attestation for the current supply, so releases are allowed.
    function attestBalanced() internal {
        attestWith(0, false);
    }

    function attestWith(uint64 delta, bool subtract) internal {
        vm.roll(block.number + 1);
        uint64 cutoffBlock = uint64(block.number - 1);
        uint64 supply = uint64(vazn.totalSupplyAt(cutoffBlock));
        uint64 balance = subtract ? supply - delta : supply + delta;
        attestationDay++;
        bytes32 statement = keccak256(abi.encode("statement", attestationDay));
        bytes32 structHash = keccak256(
            abi.encode(
                VeritasTypes.BALANCE_ATTESTATION_TYPEHASH,
                attestationDay,
                cutoffBlock,
                uint64(block.timestamp),
                balance,
                statement
            )
        );
        ledger.attestBalance(
            attestationDay,
            cutoffBlock,
            uint64(block.timestamp),
            balance,
            statement,
            sign(BANK_PK, structHash)
        );
    }

    // ------------------------------------------------------------------ Merkle trees

    /// Builds an OpenZeppelin StandardMerkleTree over the leaves and returns a proof per leaf.
    function merkle(DonationLeaf[] memory leaves)
        internal
        pure
        returns (bytes32 root, bytes32[][] memory proofs)
    {
        uint256 n = leaves.length;
        bytes32[] memory hashes = new bytes32[](n);
        uint256[] memory order = new uint256[](n);
        for (uint256 i = 0; i < n; i++) {
            hashes[i] = hashLeaf(leaves[i]);
            order[i] = i;
        }
        // Insertion sort by hash, stable like Array.prototype.sort.
        for (uint256 i = 1; i < n; i++) {
            uint256 current = order[i];
            uint256 j = i;
            while (j > 0 && hashes[order[j - 1]] > hashes[current]) {
                order[j] = order[j - 1];
                j--;
            }
            order[j] = current;
        }
        uint256 size = 2 * n - 1;
        bytes32[] memory tree = new bytes32[](size);
        uint256[] memory position = new uint256[](n);
        for (uint256 i = 0; i < n; i++) {
            tree[size - 1 - i] = hashes[order[i]];
            position[order[i]] = size - 1 - i;
        }
        for (uint256 k = size - n; k > 0; k--) {
            tree[k - 1] = hashPair(tree[2 * k - 1], tree[2 * k]);
        }
        root = tree[0];
        proofs = new bytes32[][](n);
        for (uint256 i = 0; i < n; i++) {
            uint256 index = position[i];
            uint256 depth;
            for (uint256 k = index; k > 0; k = (k - 1) / 2) {
                depth++;
            }
            bytes32[] memory path = new bytes32[](depth);
            uint256 d;
            while (index > 0) {
                path[d++] = tree[index % 2 == 1 ? index + 1 : index - 1];
                index = (index - 1) / 2;
            }
            proofs[i] = path;
        }
    }

    function hashPair(bytes32 a, bytes32 b) internal pure returns (bytes32) {
        return a < b ? keccak256(abi.encode(a, b)) : keccak256(abi.encode(b, a));
    }
}
