# DepositToken Smart Contract — Deep Dive

## Purpose

`contracts/DepositToken.sol` is the **on-chain claim instrument**. Each unit represents **one cent of USD** held in the bank treasury (2 decimals, matching fiat).

## Access control

- **`bankOperator`** — sole address allowed to `mint` and `burn`
- Institutional analog: only the **issuing bank** (JPM, Citi, or Partior operator) adjusts supply
- Transfers are peer-to-peer between institutional wallets

## Storage layout

```solidity
mapping(address => uint256) private _balances;
uint256 public totalSupply;
```

| Variable | Storage effect |
|----------|----------------|
| `_balances[alice]` | Alice's token claim |
| `totalSupply` | Aggregate tokenized deposits outstanding |

## mint() — state transition

```
PRE:  totalSupply = S,  _balances[to] = B
POST: totalSupply = S + amount,  _balances[to] = B + amount
```

**EVM operations:** `SLOAD` balance, `SSTORE` new balance, `SSTORE` supply, `LOG` Mint + Transfer(from zero address).

**Kinexys:** JPM issues deposit tokens after internal fiat earmark.  
**Citi:** Mint creates liabilities on token ledger matched to held fiat.  
**Partior:** Ledger credits after member funding confirmation.

## burn() — state transition

```
PRE:  _balances[from] >= amount
POST: _balances[from] -= amount, totalSupply -= amount
```

**Kinexys/Citi:** Detokenization — destroy claim, release fiat.  
**Partior:** Burn before or after RTGS leg depending on settlement model.

## transfer() — state transition

```
PRE:  _balances[msg.sender] >= amount
POST: sender -= amount, receiver += amount, totalSupply unchanged
```

Fiat at bank **unchanged** — only beneficial ownership of pooled deposit moves.

## Events (reconciliation)

| Event | Use |
|-------|-----|
| `Mint` | Link to mint API / GL tokenization entry |
| `Transfer` | PvP leg proof |
| `Burn` | Redemption audit |

## Why not ERC-20 OpenZeppelin in POC?

Self-contained contract avoids Node.js/npm toolchain. Production would extend audited OZ `ERC20` + `AccessControl` with regulatory hooks.
