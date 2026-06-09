// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

contract DepositToken is AccessControl, Pausable {
    string public constant name = "USD Deposit Token";
    string public constant symbol = "USDD";
    uint8 public constant decimals = 2;

    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant BURNER_ROLE = keccak256("BURNER_ROLE");
    bytes32 public constant PAUSER_ROLE = keccak256("PAUSER_ROLE");

    uint256 public totalSupply;

    mapping(address => uint256) private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;

    event Mint(address indexed to, uint256 amount, address indexed operator);
    event Burn(address indexed from, uint256 amount, address indexed operator);
    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    constructor(address bankOperator) {
        require(bankOperator != address(0), "DepositToken: zero operator");
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(MINTER_ROLE, bankOperator);
        _grantRole(BURNER_ROLE, bankOperator);
    }

    function balanceOf(address account) external view returns (uint256) {
        return _balances[account];
    }

    function allowance(address owner, address spender) external view returns (uint256) {
        return _allowances[owner][spender];
    }

    function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE) whenNotPaused {
        require(to != address(0), "DepositToken: mint to zero");
        require(amount > 0, "DepositToken: zero amount");

        totalSupply += amount;
        _balances[to] += amount;

        emit Mint(to, amount, msg.sender);
        emit Transfer(address(0), to, amount);
    }

    function burn(address from, uint256 amount) external onlyRole(BURNER_ROLE) whenNotPaused {
        require(from != address(0), "DepositToken: burn from zero");
        require(amount > 0, "DepositToken: zero amount");
        require(_balances[from] >= amount, "DepositToken: burn exceeds balance");

        _balances[from] -= amount;
        totalSupply -= amount;

        emit Burn(from, amount, msg.sender);
        emit Transfer(from, address(0), amount);
    }

    function transfer(address to, uint256 amount) external whenNotPaused returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        _allowances[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external whenNotPaused returns (bool) {
        uint256 currentAllowance = _allowances[from][msg.sender];
        require(currentAllowance >= amount, "DepositToken: insufficient allowance");
        unchecked {
            _allowances[from][msg.sender] = currentAllowance - amount;
        }
        _transfer(from, to, amount);
        return true;
    }

    function pause() external onlyRole(PAUSER_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(PAUSER_ROLE) {
        _unpause();
    }

    function _transfer(address from, address to, uint256 amount) private {
        require(from != address(0), "DepositToken: transfer from zero");
        require(to != address(0), "DepositToken: transfer to zero");
        require(amount > 0, "DepositToken: zero amount");
        require(_balances[from] >= amount, "DepositToken: insufficient balance");

        _balances[from] -= amount;
        _balances[to] += amount;

        emit Transfer(from, to, amount);
    }
}
