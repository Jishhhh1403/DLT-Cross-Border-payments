# API Examples

Base URL: `http://localhost:8000`

## Health

```bash
curl http://localhost:8000/health
```

## Initial balances

```bash
curl http://localhost:8000/balances
```

## Step 1 — Reserve fiat

```bash
curl -X POST http://localhost:8000/reserve \
  -H "Content-Type: application/json" \
  -d '{"client_id": "ALICE", "amount": 10000}'
```

Expected: `blockchain.transaction_hash` is `null` (off-chain only).

## Step 2 — Mint tokens

```bash
curl -X POST http://localhost:8000/mint \
  -H "Content-Type: application/json" \
  -d '{"client_id": "ALICE", "amount": 10000}'
```

Expected: `Mint` and `Transfer` events in `blockchain.event_logs`.

## Step 3 — Transfer

```bash
curl -X POST http://localhost:8000/transfer \
  -H "Content-Type: application/json" \
  -d '{"from_client_id": "ALICE", "to_client_id": "BOB", "amount": 10000}'
```

## Step 4 — Redeem

```bash
curl -X POST http://localhost:8000/redeem \
  -H "Content-Type: application/json" \
  -d '{"client_id": "BOB", "amount": 10000}'
```

Expected: `Burn` event; Bob fiat available = 10000.

## Sample response shape

```json
{
  "operation": "MINT",
  "status": "success",
  "message": "Minted 10000 deposit tokens...",
  "ledger": {
    "fiat_ledger": [
      {"client_id": "ALICE", "available": 90000, "reserved": 0},
      {"client_id": "BOB", "available": 0, "reserved": 0}
    ],
    "token_ledger": [
      {"client_id": "ALICE", "onchain_address": "0x7099...", "balance": 10000},
      {"client_id": "BOB", "onchain_address": "0x3C44...", "balance": 0}
    ]
  },
  "blockchain": {
    "transaction_hash": "0x...",
    "block_number": 42,
    "gas_used": 51234,
    "event_logs": [
      {"event": "Mint", "args": {"to": "0x7099...", "amount": 10000, "operator": "0xf39F..."}}
    ]
  },
  "institutional_notes": {
    "kinexys": "...",
    "citi_token_services": "...",
    "partior": "..."
  }
}
```

## Automated demo

```bash
python scripts/run_settlement_demo.py
```
