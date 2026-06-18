// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

// This is the smart contract (a digital agreement) that represents deposit tokens on the blockchain.
// Think of it like a bank's digital ledger that tracks who owns how many deposit tokens.
// It uses OpenZeppelin's building blocks for security (AccessControl) and emergency stop (Pausable).
contract DepositToken is AccessControl, Pausable {
    // These three lines are like the name, ticker symbol, and decimal places of a real-world currency.
    // "USD Deposit Token" / "USDD" — just like how USD is the code for US Dollars.
    // decimals=2 means the smallest unit is 1 cent (like $1.00 = 100 cents).
    string public constant name = "USD Deposit Token";
    string public constant symbol = "USDD";
    uint8 public constant decimals = 2;

    // These are like job titles that define what each person is allowed to do.
    // MINTER_ROLE = someone who can create (mint) new deposit tokens.
    // BURNER_ROLE = someone who can destroy (burn) deposit tokens.
    // PAUSER_ROLE = someone who can pause all transactions in an emergency.
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant BURNER_ROLE = keccak256("BURNER_ROLE");
    bytes32 public constant PAUSER_ROLE = keccak256("PAUSER_ROLE");

    // The total number of deposit tokens that exist right now (like all the cash in circulation).
    uint256 public totalSupply;

    // A private record of how many tokens each person owns. Like a bank's internal ledger.
    mapping(address => uint256) private _balances;
    // A private record of who has given permission to someone else to spend their tokens.
    // For example, Alice saying "Bob can spend up to 100 of my tokens."
    mapping(address => mapping(address => uint256)) private _allowances;

    // Events are like digital receipts or notifications that get recorded on the blockchain.
    // They let external systems know when something important happened.
    event Mint(address indexed to, uint256 amount, address indexed operator);
    event Burn(address indexed from, uint256 amount, address indexed operator);
    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    // This runs once when the contract is first created (deployed).
    // It sets up the bank as the operator who can create and destroy tokens.
    constructor(address bankOperator) {
        require(bankOperator != address(0), "DepositToken: zero operator");
        // The person who deploys the contract gets full admin control.
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        // The bank operator gets permission to create tokens (mint) and destroy them (burn).
        _grantRole(MINTER_ROLE, bankOperator);
        _grantRole(BURNER_ROLE, bankOperator);
    }

    // Check how many deposit tokens a specific person (account) has.
    // Like asking a bank "How much does Alice have in her account?"
    function balanceOf(address account) external view returns (uint256) {
        return _balances[account];
    }

    // Check how many tokens one person has allowed another person to spend on their behalf.
    // Like checking "How much has Alice authorized Bob to spend?"
    function allowance(address owner, address spender) external view returns (uint256) {
        return _allowances[owner][spender];
    }

    // Create new deposit tokens and give them to someone.
    // Only the bank (someone with MINTER_ROLE) can do this, and only when trading is not paused.
    // This is like a bank printing digital money and putting it into a customer's account.
    function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE) whenNotPaused {
        require(to != address(0), "DepositToken: mint to zero");
        require(amount > 0, "DepositToken: zero amount");

        // Increase the total tokens in circulation and add the new tokens to the person's balance.
        totalSupply += amount;
        _balances[to] += amount;

        // Record this event on the blockchain as proof.
        emit Mint(to, amount, msg.sender);
        emit Transfer(address(0), to, amount);
    }

    // Destroy (burn) deposit tokens from someone's account.
    // Only the bank (someone with BURNER_ROLE) can do this, and only when trading is not paused.
    // This is like a bank taking digital money out of circulation when a customer cashes out.
    function burn(address from, uint256 amount) external onlyRole(BURNER_ROLE) whenNotPaused {
        require(from != address(0), "DepositToken: burn from zero");
        require(amount > 0, "DepositToken: zero amount");
        // Make sure the person actually has enough tokens to burn.
        require(_balances[from] >= amount, "DepositToken: burn exceeds balance");

        // Reduce the person's balance and the total supply.
        _balances[from] -= amount;
        totalSupply -= amount;

        // Record this event on the blockchain as proof.
        emit Burn(from, amount, msg.sender);
        emit Transfer(from, address(0), amount);
    }

    // Send tokens from your own account to someone else.
    // Like transferring money from your bank account to another person's account.
    function transfer(address to, uint256 amount) external whenNotPaused returns (bool) {
        _transfer(msg.sender, to, amount);
        return true;
    }

    // Give permission to another person to spend some of your tokens.
    // Like telling your bank "Bob is allowed to withdraw up to $100 from my account."
    function approve(address spender, uint256 amount) external returns (bool) {
        _allowances[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    // Move tokens from one person's account to another, using a pre-approved allowance.
    // Someone who has been given permission (approved) can spend the token owner's tokens.
    // For example, Bob uses Alice's approval to transfer her tokens to Charlie.
    function transferFrom(address from, address to, uint256 amount) external whenNotPaused returns (bool) {
        uint256 currentAllowance = _allowances[from][msg.sender];
        // Check that the spender hasn't exceeded their approved limit.
        require(currentAllowance >= amount, "DepositToken: insufficient allowance");
        unchecked {
            // Reduce the remaining allowance by the amount being transferred.
            _allowances[from][msg.sender] = currentAllowance - amount;
        }
        _transfer(from, to, amount);
        return true;
    }

    // Emergency stop — pause all token transfers, minting, and burning.
    // Only someone with PAUSER_ROLE can do this.
    // This is like a bank freezing all accounts during a security incident.
    function pause() external onlyRole(PAUSER_ROLE) {
        _pause();
    }

    // Resume normal operations after an emergency pause.
    // Only someone with PAUSER_ROLE can do this.
    function unpause() external onlyRole(PAUSER_ROLE) {
        _unpause();
    }

    // The internal function that actually moves tokens from one account to another.
    // Both "transfer" and "transferFrom" use this behind the scenes.
    // It's private (internal) so only the transfer functions above can call it.
    function _transfer(address from, address to, uint256 amount) private {
        require(from != address(0), "DepositToken: transfer from zero");
        require(to != address(0), "DepositToken: transfer to zero");
        require(amount > 0, "DepositToken: zero amount");
        // Make sure the sender has enough tokens to send.
        require(_balances[from] >= amount, "DepositToken: insufficient balance");

        // Subtract from the sender and add to the receiver.
        _balances[from] -= amount;
        _balances[to] += amount;

        // Record the transfer on the blockchain.
        emit Transfer(from, to, amount);
    }
}
