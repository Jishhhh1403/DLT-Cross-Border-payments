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

from fastapi import FastAPI, Header, HTTPException

from backend.app.blockchain.client import BesuClient
from backend.app.fiat_ledger import FiatLedger
from backend.app.models import MintRequest, RedeemRequest, ReserveRequest, TransferRequest
from backend.app.settlement import SettlementOrchestrator


# Create the main components our app needs to work:
# 1. A ledger to track real-world money (fiat currency like USD).
# 2. A connection to the blockchain (Besu) for digital tokens.
# 3. An orchestrator that coordinates between the two.
fiat_ledger = FiatLedger()
besu_client = BesuClient()
orchestrator: SettlementOrchestrator | None = None


# This runs when the server starts up.
# It checks the blockchain is reachable, loads the smart contract, and gets everything ready.
@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    if not besu_client.connected:
        raise RuntimeError(
            f"Cannot connect to Besu at {besu_client.w3.provider.endpoint_uri}"
        )
    besu_client.load_or_deploy_contract()
    orchestrator = SettlementOrchestrator(fiat_ledger, besu_client)
    yield


# Set up the web API with a name and description.
# This tells anyone who visits what this service does.
app = FastAPI(
    title="Tokenized Deposit Settlement POC",
    description=(
        "Institutional cross-border settlement using tokenized deposits on Hyperledger Besu. "
        "Fiat is off-chain; tokens are on-chain claims on bank-held deposits."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# Get the orchestrator — the brain that coordinates all the steps.
# If it's not ready yet, return an error.
def _orch() -> SettlementOrchestrator:
    if orchestrator is None:
        raise HTTPException(503, "Settlement engine not initialized")
    return orchestrator


# Make sure we have a unique ID for each request.
# This helps prevent the same request from being processed twice by accident.
def _resolve_key(req, header: str | None) -> str:
    return header or req.idempotency_key or str(uuid4())


# A simple health-check endpoint.
# Like a doctor checking your pulse — tells other systems if this server is alive and well.
@app.get("/health")
def health():
    return {
        "status": "ok",
        "besu_connected": besu_client.connected,
        "chain_id": besu_client.w3.eth.chain_id,
        "latest_block": besu_client.w3.eth.block_number,
        "contract": besu_client.contract.address if besu_client._contract else None,
    }


# Step 1: Reserve money (fiat).
# A customer tells the bank "I want to set aside $100 from my account for tokenization."
# This only touches the bank's internal ledger — no blockchain involved yet.
@app.post("/reserve")
def reserve(
    req: ReserveRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    req.idempotency_key = _resolve_key(req, idempotency_key)
    try:
        return _orch().reserve(req)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# Step 2: Mint deposit tokens.
# The bank converts the reserved fiat money into digital deposit tokens on the blockchain.
# Now the customer has digital tokens that represent their real money.
@app.post("/mint")
def mint(
    req: MintRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    req.idempotency_key = _resolve_key(req, idempotency_key)
    try:
        return _orch().mint(req)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# Step 3: Transfer tokens from one person to another.
# Alice sends her digital deposit tokens to Bob on the blockchain.
# This is like a digital wire transfer but using tokens instead of traditional money.
@app.post("/transfer")
def transfer(
    req: TransferRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    req.idempotency_key = _resolve_key(req, idempotency_key)
    try:
        return _orch().transfer(req)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


# Step 4: Redeem tokens back to real money.
# Bob wants to cash out — the bank destroys (burns) the tokens and credits Bob's bank account.
# This converts digital tokens back into real fiat currency.
@app.post("/redeem")
def redeem(
    req: RedeemRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    req.idempotency_key = _resolve_key(req, idempotency_key)
    try:
        return _orch().redeem(req)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


# Check everyone's balances — both their fiat (real money) and their tokens (digital money).
@app.get("/balances")
def balances():
    return _orch().balances()
