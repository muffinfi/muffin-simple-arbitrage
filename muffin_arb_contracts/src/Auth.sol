// SPDX-License-Identifier: GPL-3.0-only
pragma solidity ^0.8.10;

abstract contract Auth {
    address public immutable owner;
    address public immutable mainExecutor;
    mapping(address => bool) public isExecutor;

    constructor(address _owner, address _mainExecutor) {
        owner = _owner;
        mainExecutor = _mainExecutor;
        isExecutor[_mainExecutor] = true;
    }

    modifier onlyOwner() {
        require(msg.sender == owner);
        _;
    }

    modifier onlyOwnerOrExecutor() {
        require(msg.sender == mainExecutor || msg.sender == owner || isExecutor[msg.sender]);
        _;
    }

    function authorize(address account, bool isAuthorized) external onlyOwner {
        require(account != mainExecutor);
        isExecutor[account] = isAuthorized;
    }
}
