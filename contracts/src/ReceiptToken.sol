// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {DonationLeaf, VeritasTypes} from "./libraries/VeritasTypes.sol";
import {Signatures} from "./libraries/Signatures.sol";
import {IDonationLedger, IVeritasHub} from "./interfaces/IVeritas.sol";

/// @notice ERC-5192: minimal soulbound NFTs.
interface IERC5192 {
    event Locked(uint256 tokenId);
    event Unlocked(uint256 tokenId);

    function locked(uint256 tokenId) external view returns (bool);
}

/// @title ReceiptToken
/// @notice One locked receipt per donor key per project: the donor's on-chain identity there.
/// @dev Anyone can mint a receipt by proving a leaf of that holder in a settled batch, so a
/// receipt always stands for a real donation. The token id comes from (project, holder), the
/// key the donor's leaves name. The owner is whoever controls that holder now: the holder
/// itself, until a key rotation moves the receipt to a new key. Votes and refund choices are
/// checked against `controllerOf`, so a donor who loses their phone keeps their rights.
///
/// Rotation after a lost phone is requested by the relayer once the donor has proved who they
/// are again off-chain, and waits 48 hours, during which the current key can cancel it. A donor
/// who still has their key can rotate at once with a signature.
contract ReceiptToken is ERC721, IERC5192 {
    uint256 public constant ROTATION_DELAY = 48 hours;

    struct Receipt {
        bytes16 projectId;
        address holder;
    }

    struct Rotation {
        address newKey;
        uint64 readyAt;
    }

    IVeritasHub public immutable hub;
    mapping(uint256 => Receipt) public receipts;
    mapping(uint256 => Rotation) public pendingRotation;
    mapping(uint256 => uint64) public rotationNonce;
    mapping(bytes16 => uint32) public holderCount;
    bool private _rotating;

    event ReceiptMinted(uint256 indexed receiptId, bytes16 indexed projectId, address holder);
    event RotationRequested(uint256 indexed receiptId, address newKey, uint64 readyAt);
    event RotationCancelled(uint256 indexed receiptId, address newKey);
    event KeyRotated(uint256 indexed receiptId, address oldKey, address newKey);

    error ReceiptsAreLocked();
    error NotRelayer();
    error UnknownReceipt(uint256 receiptId);
    error BadNewKey();
    error NoPendingRotation();
    error RotationNotReady(uint64 readyAt);
    error Expired();

    constructor(IVeritasHub hub_) ERC721("Veritas Donation Receipt", "VRCPT") {
        hub = hub_;
    }

    function receiptId(bytes16 projectId, address holder) public pure returns (uint256) {
        return uint256(keccak256(abi.encode(projectId, holder)));
    }

    /// @notice Mints the receipt for a leaf's holder. Does nothing if it already exists.
    function mint(uint64 batchId, DonationLeaf calldata leaf, bytes32[] calldata proof)
        external
        returns (uint256 id)
    {
        IDonationLedger(hub.ledger()).verifyLeaf(batchId, leaf, proof);
        id = receiptId(leaf.projectId, leaf.holder);
        if (_ownerOf(id) != address(0)) return id;
        receipts[id] = Receipt(leaf.projectId, leaf.holder);
        holderCount[leaf.projectId]++;
        _mint(leaf.holder, id);
        emit ReceiptMinted(id, leaf.projectId, leaf.holder);
        emit Locked(id);
    }

    /// @notice The key that may sign for a holder in a project.
    function controllerOf(bytes16 projectId, address holder) external view returns (address) {
        address owner = _ownerOf(receiptId(projectId, holder));
        return owner == address(0) ? holder : owner;
    }

    function locked(uint256 tokenId) external view returns (bool) {
        _requireOwned(tokenId);
        return true;
    }

    function requestRotation(uint256 id, address newKey) external {
        if (msg.sender != hub.relayer()) revert NotRelayer();
        address owner = _owner(id);
        if (newKey == address(0) || newKey == owner) revert BadNewKey();
        uint64 readyAt = uint64(block.timestamp + ROTATION_DELAY);
        pendingRotation[id] = Rotation(newKey, readyAt);
        emit RotationRequested(id, newKey, readyAt);
    }

    /// @notice The current key refuses a pending rotation, for example one requested by someone
    /// who stole the donor's phone number. The refusal names the request's readyAt, so it
    /// refuses that request only and cannot be replayed against a later one.
    function cancelRotation(uint256 id, bytes calldata signature) external {
        Rotation memory pending = pendingRotation[id];
        if (pending.newKey == address(0)) revert NoPendingRotation();
        bytes32 structHash = keccak256(
            abi.encode(VeritasTypes.ROTATION_CANCEL_TYPEHASH, id, pending.newKey, pending.readyAt)
        );
        Signatures.check(hub, _owner(id), structHash, signature);
        delete pendingRotation[id];
        emit RotationCancelled(id, pending.newKey);
    }

    function finalizeRotation(uint256 id) external {
        Rotation memory pending = pendingRotation[id];
        if (pending.newKey == address(0)) revert NoPendingRotation();
        if (block.timestamp < pending.readyAt) revert RotationNotReady(pending.readyAt);
        delete pendingRotation[id];
        _moveTo(id, pending.newKey);
    }

    /// @notice A donor who still has their key moves the receipt to a new one at once.
    function rotateBySig(uint256 id, address newKey, uint64 deadline, bytes calldata signature)
        external
    {
        if (block.timestamp > deadline) revert Expired();
        address owner = _owner(id);
        if (newKey == address(0) || newKey == owner) revert BadNewKey();
        bytes32 structHash = keccak256(
            abi.encode(VeritasTypes.KEY_ROTATION_TYPEHASH, id, newKey, rotationNonce[id], deadline)
        );
        Signatures.check(hub, owner, structHash, signature);
        rotationNonce[id]++;
        delete pendingRotation[id];
        _moveTo(id, newKey);
    }

    function approve(address, uint256) public pure override {
        revert ReceiptsAreLocked();
    }

    function setApprovalForAll(address, bool) public pure override {
        revert ReceiptsAreLocked();
    }

    function supportsInterface(bytes4 interfaceId) public view override returns (bool) {
        return interfaceId == type(IERC5192).interfaceId || super.supportsInterface(interfaceId);
    }

    function _moveTo(uint256 id, address newKey) private {
        address oldKey = _owner(id);
        _rotating = true;
        _update(newKey, id, address(0));
        _rotating = false;
        emit KeyRotated(id, oldKey, newKey);
    }

    function _owner(uint256 id) private view returns (address owner) {
        owner = _ownerOf(id);
        if (owner == address(0)) revert UnknownReceipt(id);
    }

    function _update(address to, uint256 tokenId, address auth)
        internal
        override
        returns (address)
    {
        if (_ownerOf(tokenId) != address(0) && !_rotating) {
            revert ReceiptsAreLocked();
        }
        return super._update(to, tokenId, auth);
    }
}
