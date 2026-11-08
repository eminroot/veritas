// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {SignatureChecker} from "@openzeppelin/contracts/utils/cryptography/SignatureChecker.sol";
import {IVeritasHub} from "../interfaces/IVeritas.sol";

/// @notice Checks a party's EIP-712 signature in the Veritas domain.
/// @dev SignatureChecker accepts a plain key (ECDSA, low-s only) or a contract that implements
/// ERC-1271, so officers, charities and the bank can sign with a Safe multisig.
library Signatures {
    error BadSignature(address signer);

    function check(IVeritasHub hub, address signer, bytes32 structHash, bytes calldata signature)
        internal
        view
    {
        bytes32 digest = hub.hashTypedData(structHash);
        if (
            signer == address(0) || !SignatureChecker.isValidSignatureNow(signer, digest, signature)
        ) {
            revert BadSignature(signer);
        }
    }
}
