// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Checkpoints} from "@openzeppelin/contracts/utils/structs/Checkpoints.sol";
import {IVeritasHub} from "./interfaces/IVeritas.sol";

/// @title vAZN
/// @notice The manat mirror: 1 vAZN is 1 manat in the partner bank's escrow account.
/// @dev Amounts are qəpik, so decimals is 2. Only the DonationLedger mints (against a bank
/// signature) and only the BankPayoutVault burns (against the bank's payout or refund
/// confirmation). It can only sit in and move between Veritas contracts, so it cannot leave
/// the system or be traded. The total supply is checkpointed per block, so the daily bank
/// attestation is compared with the supply at the bank's cut-off block, not at whatever block
/// the attestation happens to land in.
contract VAZN is ERC20 {
    using Checkpoints for Checkpoints.Trace208;

    IVeritasHub public immutable hub;
    Checkpoints.Trace208 private _supplyHistory;

    error OnlyLedger();
    error OnlyVault();
    error NotVeritasContract(address account);
    error ApprovalsDisabled();
    error FutureBlock(uint256 blockNumber);

    constructor(IVeritasHub hub_) ERC20("Veritas Manat", "vAZN") {
        hub = hub_;
    }

    function decimals() public pure override returns (uint8) {
        return 2;
    }

    function mint(address to, uint256 amount) external {
        if (msg.sender != hub.ledger()) revert OnlyLedger();
        _mint(to, amount);
    }

    function burn(address from, uint256 amount) external {
        if (msg.sender != hub.vault()) revert OnlyVault();
        _burn(from, amount);
    }

    /// @notice Supply at the end of a past block.
    function totalSupplyAt(uint256 blockNumber) external view returns (uint256) {
        if (blockNumber >= block.number) revert FutureBlock(blockNumber);
        return _supplyHistory.upperLookupRecent(uint48(blockNumber));
    }

    function approve(address, uint256) public pure override returns (bool) {
        revert ApprovalsDisabled();
    }

    function _update(address from, address to, uint256 value) internal override {
        if (from != address(0) && !_isVeritas(from)) revert NotVeritasContract(from);
        if (to != address(0) && !_isVeritas(to)) revert NotVeritasContract(to);
        super._update(from, to, value);
        if (from == address(0) || to == address(0)) {
            _supplyHistory.push(uint48(block.number), uint208(totalSupply()));
        }
    }

    function _isVeritas(address account) private view returns (bool) {
        return hub.isEscrow(account) || account == hub.vault();
    }
}
