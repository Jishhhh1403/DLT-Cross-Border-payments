"""
FastAPI settlement API — institutional tokenized deposit POC.

Endpoints mirror a production payment orchestration service:
  reserve -> mint -> transfer -> redeem

An `Idempotency-Key` header can be provided for Saga safety.
If omitted, a UUID is auto-generated per request.
"""

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException

from backend.app.blockchain.client import BesuClient
from backend.app.fiat_ledger import FiatLedger
from backend.app.models import MintRequest, RedeemRequest, ReserveRequest, TransferRequest
from backend.app.settlement import SettlementOrchestrator


fiat_ledger = FiatLedger()
besu_client = BesuClient()
orchestrator: SettlementOrchestrator | None = None


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


app = FastAPI(
    title="Tokenized Deposit Settlement POC",
    description=(
        "Institutional cross-border settlement using tokenized deposits on Hyperledger Besu. "
        "Fiat is off-chain; tokens are on-chain claims on bank-held deposits."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


def _orch() -> SettlementOrchestrator:
    if orchestrator is None:
        raise HTTPException(503, "Settlement engine not initialized")
    return orchestrator


def _resolve_key(req, header: str | None) -> str:
    return header or req.idempotency_key or str(uuid4())


@app.get("/health")
def health():
    return {
        "status": "ok",
        "besu_connected": besu_client.connected,
        "chain_id": besu_client.w3.eth.chain_id,
        "latest_block": besu_client.w3.eth.block_number,
        "contract": besu_client.contract.address if besu_client._contract else None,
    }


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


@app.get("/balances")
def balances():
    return _orch().balances()
