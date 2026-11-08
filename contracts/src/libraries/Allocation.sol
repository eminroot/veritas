// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {VeritasTypes} from "./VeritasTypes.sol";

/// @notice Splits an amount over milestones, exactly like `veritas.domain.allocation.allocate`.
/// @dev Used when a redirect brings money into a project. Pro rata uses the largest remainder
/// method, the earlier milestone winning a tie; sequential fills the earliest milestone that
/// still needs money. Python vectors check both in `test/Vectors.t.sol`.
library Allocation {
    error NothingToAllocate();
    error Overfunded(uint256 amount, uint256 needed);
    error UnknownRule(uint8 rule);

    function allocate(uint64 amount, uint64[] memory remaining, uint8 rule)
        internal
        pure
        returns (uint64[] memory parts)
    {
        if (amount == 0) revert NothingToAllocate();
        uint256 needed;
        for (uint256 i = 0; i < remaining.length; i++) {
            needed += remaining[i];
        }
        if (amount > needed) revert Overfunded(amount, needed);
        parts = new uint64[](remaining.length);

        if (rule == VeritasTypes.ALLOCATION_SEQUENTIAL) {
            uint64 left = amount;
            for (uint256 i = 0; i < remaining.length && left > 0; i++) {
                uint64 take = remaining[i] < left ? remaining[i] : left;
                parts[i] = take;
                left -= take;
            }
            return parts;
        }
        if (rule != VeritasTypes.ALLOCATION_PRO_RATA) revert UnknownRule(rule);

        uint256[] memory remainders = new uint256[](remaining.length);
        uint256 given;
        for (uint256 i = 0; i < remaining.length; i++) {
            uint256 scaled = uint256(amount) * remaining[i];
            parts[i] = uint64(scaled / needed);
            remainders[i] = scaled % needed;
            given += parts[i];
        }
        // At most one qəpik per milestone is left over, and every one of them goes to a part with
        // a non-zero remainder, so a milestone that needs nothing never gets anything.
        for (uint256 left = amount - given; left > 0; left--) {
            uint256 best;
            for (uint256 i = 1; i < remaining.length; i++) {
                if (remainders[i] > remainders[best]) best = i;
            }
            parts[best] += 1;
            remainders[best] = 0;
        }
    }
}
