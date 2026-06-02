# File Guide — Why Each File Exists

## Root

| File | Why | Interacts with | Banking parallel |
|------|-----|----------------|------------------|
| `docker-compose.yml` | Runs Besu + API together | `besu/`, `backend/` | Hosted settlement stack |
| `README.md` | Entry point | All docs | — |

## `besu/`

| File | Why | Interacts with |
|------|-----|----------------|
| `genesis/genesis-ibft.json` | Chain rules + prefunded accounts + validator set | Besu container |
| `config/config.toml` | Node tuning (sync, P2P) | Besu container |
| `config/keys/validator.key` | IBFT block signer identity | Must match genesis extraData |

## `contracts/`

| File | Why | Interacts with |
|------|-----|----------------|
| `DepositToken.sol` | Tokenized deposit logic on-ledger | Deployed via `deploy_contract.py`, called via `client.py` |

## `backend/`

| File | Why | Interacts with |
|------|-----|----------------|
| `main.py` | HTTP API surface | `settlement.py` |
| `app/fiat_ledger.py` | Off-chain money | `settlement.py` only |
| `app/settlement.py` | Workflow coordinator | fiat + blockchain |
| `app/blockchain/client.py` | web3.py adapter | Besu RPC |
| `app/models.py` | API contracts | FastAPI |
| `app/config.py` | Environment | All backend |

## `scripts/`

| File | Why |
|------|-----|
| `wait_for_besu.py` | Startup ordering |
| `deploy_contract.py` | One-time contract deploy |
| `run_settlement_demo.py` | Full lifecycle demo |

## `docs/`

Educational artifacts — walkthrough, sequences, scaling, API examples.
