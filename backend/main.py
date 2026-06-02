"""
FastAPI settlement API — institutional tokenized deposit POC.

Endpoints mirror a production payment orchestration service:
  reserve → mint → transfer → redeem
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

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
def reserve(req: ReserveRequest):
    """Off-chain: lock fiat from available → reserved."""
    try:
        return _orch().reserve(req)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/mint")
def mint(req: MintRequest):
    """On-chain: mint deposit tokens after fiat reserved."""
    try:
        return _orch().mint(req)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.post("/transfer")
def transfer(req: TransferRequest):
    """On-chain: transfer tokens between institutional wallets."""
    try:
        return _orch().transfer(req)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@app.post("/redeem")
def redeem(req: RedeemRequest):
    """On-chain burn + off-chain fiat credit."""
    try:
        return _orch().redeem(req)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@app.get("/balances")
def balances():
    """Fiat + on-chain token balances with full observability."""
    return _orch().balances()
