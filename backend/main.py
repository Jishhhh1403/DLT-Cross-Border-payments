"""
FastAPI settlement API — institutional tokenized deposit POC.

This is the main web server that other programs talk to (the API).
It provides the four key payment steps: reserve -> mint -> transfer -> redeem.
Think of it like a bank's online banking API that apps use to move money.

An `Idempotency-Key` header can be provided to prevent double-processing.
If you don't provide one, a unique ID is automatically created for each request.
"""

# Import the tools we need: web framework, blockchain connection, and the payment orchestrator.
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Depends

from backend.app.blockchain.client import BesuClient
from backend.app.database import get_session, init_db
from backend.app.fiat_ledger import FiatLedger
from backend.app.models import MintRequest, RedeemRequest, ReserveRequest, TransferRequest
from backend.app.settlement import SettlementOrchestrator


# Create the main components our app needs to work:
# 1. A connection to the blockchain (Besu).
besu_client = BesuClient()
# The orchestrator is now created per-request because it depends on a DB session.
orchestrator: SettlementOrchestrator | None = None


def get_db():
    db = get_session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# This runs when the server starts up.
@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    if not besu_client.connected:
        raise RuntimeError(
            f"Cannot connect to Besu at {besu_client.w3.provider.endpoint_uri}"
        )
    init_db()
    from backend.app.database import seed_db, load_wallets
    seed_db()
    wallets = load_wallets()
    besu_client.load_wallets(wallets)
    besu_client.load_or_deploy_contract()
    yield


# Set up the web API with a name and description.
app = FastAPI(
    title="Tokenized Deposit Settlement POC",
    description=(
        "Institutional cross-border settlement using tokenized deposits on Hyperledger Besu. "
        "Fiat is off-chain; tokens are on-chain claims on bank-held deposits."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# Helper to create the orchestrator with the current database session.
def _get_orchestrator(db=Depends(get_db)) -> SettlementOrchestrator:
    return SettlementOrchestrator(FiatLedger(db), besu_client)


# Make sure we have a unique ID for each request.
def _resolve_key(req, header: str | None) -> str:
    return header or req.idempotency_key or str(uuid4())


# A simple health-check endpoint.
@app.get("/health")
def health(db=Depends(get_db)):
    return {
        "status": "ok",
        "besu_connected": besu_client.connected,
        "chain_id": besu_client.w3.eth.chain_id,
        "latest_block": besu_client.w3.eth.block_number,
        "contract": besu_client.contract.address if besu_client._contract else None,
    }


# Step 1: Reserve money (fiat).
@app.post("/reserve")
def reserve(
    req: ReserveRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    orch=Depends(_get_orchestrator),
):
    req.idempotency_key = _resolve_key(req, idempotency_key)
    try:
        return orch.reserve(req)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# Step 2: Mint deposit tokens.
@app.post("/mint")
def mint(
    req: MintRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    orch=Depends(_get_orchestrator),
):
    req.idempotency_key = _resolve_key(req, idempotency_key)
    try:
        return orch.mint(req)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# Step 3: Transfer tokens from one person to another.
@app.post("/transfer")
def transfer(
    req: TransferRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    orch=Depends(_get_orchestrator),
):
    req.idempotency_key = _resolve_key(req, idempotency_key)
    try:
        return orch.transfer(req)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


# Step 4: Redeem tokens back to real money.
@app.post("/redeem")
def redeem(
    req: RedeemRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    orch=Depends(_get_orchestrator),
):
    req.idempotency_key = _resolve_key(req, idempotency_key)
    try:
        return orch.redeem(req)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


# Check everyone's balances — both their fiat and their tokens.
@app.get("/balances")
def balances(orch=Depends(_get_orchestrator)):
    return orch.balances()
