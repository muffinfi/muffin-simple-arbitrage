// SPDX-License-Identifier: GPL-3.0-only
pragma solidity ^0.8.10;

import "./Auth.sol";

abstract contract Multicall is Auth {
    struct Call {
        address payable target;
        uint256 value;
        bytes callData;
    }

    struct Result {
        bool success;
        bytes returnData;
    }

    function _require(bool success, bytes memory returnData) internal pure {
        if (!success) {
            assembly {
                revert(add(32, returnData), mload(returnData))
            }
        }
    }

    function multicall(bool requireSuccess, Call[] calldata calls)
        external
        payable
        onlyOwner
        returns (Result[] memory results)
    {
        results = new Result[](calls.length);
        for (uint256 i = 0; i < calls.length; i++) {
            Call memory call = calls[i];
            (bool success, bytes memory ret) = call.target.call{value: call.value}(call.callData);
            if (requireSuccess) _require(success, ret);
            results[i] = Result(success, ret);
        }
    }

    function multiDelegatecall(bool requireSuccess, bytes[] calldata calls)
        external
        payable
        onlyOwner
        returns (Result[] memory results)
    {
        results = new Result[](calls.length);
        for (uint256 i = 0; i < calls.length; i++) {
            (bool success, bytes memory ret) = address(this).delegatecall(calls[i]);
            if (requireSuccess) _require(success, ret);
            results[i] = Result(success, ret);
        }
    }
}
