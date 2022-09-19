// SPDX-License-Identifier: GPL-3.0-only
pragma solidity ^0.8.10;

import "./Multicall.sol";
import "./Auth.sol";

// prettier-ignore
interface IERC20 {
    function balanceOf(address owner) external view returns (uint);
    function transfer(address to, uint value) external returns (bool);
}

// prettier-ignore
interface IWETH is IERC20 {
    function deposit() external payable;
    function withdraw(uint256) external;
}

contract Arbitrageur4 is Multicall {
    address public immutable hub;
    address public immutable weth;

    constructor(
        address _hub,
        address _weth,
        address _owner,
        address _executor
    ) Auth(_owner, _executor) {
        hub = _hub;
        weth = _weth;
    }

    receive() external payable {}

    modifier ensureProfitAndPayFee(
        address tokenIn,
        uint256 amtNetMin,
        uint256 txFeeEth
    ) {
        uint256 balanceBefore = IERC20(tokenIn).balanceOf(address(this));
        _;
        uint256 balanceAfter = IERC20(tokenIn).balanceOf(address(this));
        require(balanceAfter >= balanceBefore + amtNetMin, "not profitable");

        if (txFeeEth > 0) {
            uint256 ethBalance = address(this).balance;
            if (ethBalance < txFeeEth) IWETH(weth).withdraw(txFeeEth - ethBalance);
            block.coinbase.transfer(txFeeEth);
        }
    }

    function work(
        address tokenIn,
        uint256 amtNetMin,
        uint256 txFeeEth,
        bytes calldata data
    ) external payable onlyOwnerOrExecutor ensureProfitAndPayFee(tokenIn, amtNetMin, txFeeEth) {
        (bool success, bytes memory ret) = hub.call(data);
        _require(success, ret);
    }

    function muffinSwapCallback(
        address tokenToMfn,
        address tokenFromMfn,
        uint256 amtToMfn,
        uint256, // amtFromMfn,
        bytes calldata data
    ) external {
        require(msg.sender == hub, "who are u?");

        (address uniV2Pool, bytes memory data2, uint256 amtToUni) = abi.decode(data, (address, bytes, uint256));

        // "amtToUni==0" means muffin first
        if (amtToUni == 0) {
            // token transfer flow:
            // 1. muffin -> univ2   (owe muffin)
            // 2. univ2  -> here    (owe muffin)
            // 3. here   -> muffin
            (bool success, bytes memory ret) = uniV2Pool.call(data2);
            _require(success, ret);
            IERC20(tokenToMfn).transfer(msg.sender, amtToMfn); // send token to hub
        } else {
            // token transfer flow:
            // 1. muffin -> here    (owe muffin)
            // 2. here   -> univ2   (owe muffin)
            // 3. univ2  -> muffin
            IERC20(tokenFromMfn).transfer(uniV2Pool, amtToUni);
            (bool success, bytes memory ret) = uniV2Pool.call(data2);
            _require(success, ret);
        }
    }
}
