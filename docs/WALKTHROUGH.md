# End-to-End Walkthrough — Alice sends $100 to Bob

Amount: **10,000 cents** ($100.00). Token decimals = 2 (same as fiat).

## Initial state

### Fiat ledger (off-chain)

| Client | Available | Reserved |
|--------|-----------|----------|
| ALICE | 100,000 ($1,000) | 0 |
| BOB | 0 | 0 |

### Token ledger (on-chain)

| Client | Balance |
|--------|---------|
| ALICE | 0 |
| BOB | 0 |

---

## Step 1 — POST /reserve

**Request:** `{"client_id": "ALICE", "amount": 10000}`

**What happens:**
- Off-chain only — **no blockchain transaction**
- Alice `available` 100,000 → 90,000
- Alice `reserved` 0 → 10,000

**Banking:** Kinexys earmarks fiat before mint. Citi places hold on funding account. Partior member confirms nostro sufficiency.

### After reserve

| Client | Available | Reserved |
|--------|-----------|----------|
| ALICE | 90,000 | 10,000 |
| BOB | 0 | 0 |

---

## Step 2 — POST /mint

**Request:** `{"client_id": "ALICE", "amount": 10000}`

**What happens:**
1. Off-chain: Alice `reserved` 10,000 → 0 (fiat remains at bank, now "tokenized")
2. On-chain: `DepositToken.mint(AliceAddress, 10000)` by bank operator
3. State change:
   - `totalSupply += 10000`
   - `_balances[Alice] += 10000`
4. Events: `Mint`, `Transfer(0x0, Alice, 10000)`

**Blockchain transaction explained:**
- **Input:** signed tx from bank operator calling `mint`
- **EVM execution:** SLOAD Alice balance, SSTORE new balance, SSTORE totalSupply
- **Receipt:** `transactionHash`, `blockNumber`, logs for reconciliation

### After mint

| Fiat | ALICE avail 90,000 | reserved 0 |
| Tokens | ALICE 10,000 | BOB 0 |

---

## Step 3 — POST /transfer

**Request:** `{"from_client_id": "ALICE", "to_client_id": "BOB", "amount": 10000}`

**What happens:**
1. Off-chain fiat: **unchanged** (money still in bank pool)
2. On-chain: Alice signs `transfer(Bob, 10000)`
3. State:
   - `_balances[Alice] -= 10000`
   - `_balances[Bob] += 10000`
4. Event: `Transfer(Alice, Bob, 10000)`

**Banking:** Kinexys atomic token move. Citi ledger updates beneficial ownership. Partior shared ledger — both members see same truth.

### After transfer

| Fiat | unchanged |
| Tokens | ALICE 0 | BOB 10,000 |

---

## Step 4 — POST /redeem

**Request:** `{"client_id": "BOB", "amount": 10000}`

**What happens:**
1. On-chain: `burn(Bob, 10000)` by bank operator
   - `_balances[Bob] -= 10000`
   - `totalSupply -= 10000`
2. Off-chain: Bob `available` 0 → 10,000

### Final state

| Client | Fiat Available | Fiat Reserved | Tokens |
|--------|----------------|---------------|--------|
| ALICE | 90,000 ($900) | 0 | 0 |
| BOB | 10,000 ($100) | 0 | 0 |

**Conservation check:** Alice lost $100 available; Bob gained $100 available. On-chain supply back to 0.

---

## Blockchain state transitions summary

| Operation | totalSupply | Alice tokens | Bob tokens | Tx? |
|-----------|-------------|--------------|------------|-----|
| Start | 0 | 0 | 0 | — |
| Reserve | 0 | 0 | 0 | No |
| Mint | 10000 | 10000 | 0 | Yes |
| Transfer | 10000 | 0 | 10000 | Yes |
| Redeem | 0 | 0 | 0 | Yes |

---

## How token balances are stored on-chain

Solidity mapping `mapping(address => uint256) private _balances` stores each wallet's balance in a **storage slot** derived from `keccak256(abi.encode(account, balances_slot))`.

`balanceOf(addr)` performs an `SLOAD` on that slot — O(1) read, auditable via Merkle Patricia trie under Besu's world state.
