// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title DepositToken
 * @notice Institutional tokenized deposit representation on a permissioned ledger.
 *
 * Each token unit represents a claim on fiat held in the bank's off-chain treasury.
 * This is NOT a cryptocurrency — mint/burn are strictly controlled by the issuing bank node.
 *
 * Banking parallels:
 * - Kinexys: JPM deposit tokens on permissioned Ethereum-derived networks
 * - Citi Token Services: bank-issued deposit tokens with centralized mint authority
 * - Partior: shared ledger tokens backed by nostro/vostro balances at member banks
 */
contract DepositToken {
    string public constant name = "USD Deposit Token";
    string public constant symbol = "USDD";
    uint8 public constant decimals = 2; // cents precision, like fiat

    address public bankOperator;
    uint256 public totalSupply;

    mapping(address => uint256) private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event Mint(address indexed to, uint256 amount, address indexed operator);
    event Burn(address indexed from, uint256 amount, address indexed operator);
    event BankOperatorTransferred(address indexed previousOperator, address indexed newOperator);

    modifier onlyBankOperator() {
        require(msg.sender == bankOperator, "DepositToken: caller is not bank operator");
        _;
    }

    constructor(address initialBankOperator) {
        require(initialBankOperator != address(0), "DepositToken: zero operator");
        bankOperator = initialBankOperator;
    }

    /**
     * @notice On-chain token balances live in `_balances` mapping (storage slot per address).
     * `balanceOf` reads that slot — institutional reconciliation compares this to off-chain records.
     */
    function balanceOf(address account) external view returns (uint256) {
        return _balances[account];
    }

    function allowance(address owner, address spender) external view returns (uint256) {
        return _allowances[owner][spender];
    }

    /**
     * @notice Mint creates new supply when fiat is reserved and tokenized.
     * State: totalSupply += amount, _balances[to] += amount
     * Only bank operator — mirrors Kinexys/Citi mint authority.
     */
    function mint(address to, uint256 amount) external onlyBankOperator {
        require(to != address(0), "DepositToken: mint to zero");
        require(amount > 0, "DepositToken: zero amount");

        totalSupply += amount;
        _balances[to] += amount;

        emit Mint(to, amount, msg.sender);
        emit Transfer(address(0), to, amount);
    }

    /**
     * @notice Peer transfer of tokenized deposits between institutional wallets on-ledger.
     */
    function transfer(address to, uint256 amount) external returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        _allowances[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 currentAllowance = _allowances[from][msg.sender];
        require(currentAllowance >= amount, "DepositToken: insufficient allowance");
        unchecked {
            _allowances[from][msg.sender] = currentAllowance - amount;
        }
        _transfer(from, to, amount);
        return true;
    }

    /**
     * @notice Burn destroys tokens when fiat is released from tokenized form.
     * State: totalSupply -= amount, _balances[from] -= amount
     */
    function burn(address from, uint256 amount) external onlyBankOperator {
        require(from != address(0), "DepositToken: burn from zero");
        require(amount > 0, "DepositToken: zero amount");
        require(_balances[from] >= amount, "DepositToken: burn exceeds balance");

        _balances[from] -= amount;
        totalSupply -= amount;

        emit Burn(from, amount, msg.sender);
        emit Transfer(from, address(0), amount);
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
