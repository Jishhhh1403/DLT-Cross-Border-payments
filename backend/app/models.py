"""Request/response schemas and transaction state models for settlement API."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    RESERVED = "RESERVED"
    ONCHAIN_SUBMITTED = "ONCHAIN_SUBMITTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TransactionRecord(BaseModel):
    idempotency_key: str
    operation_type: str
    status: TransactionStatus
    client_id: str | None = None
    to_client_id: str | None = None
    amount: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: str | None = None


class ReserveRequest(BaseModel):
    client_id: str = Field(..., description="Institutional client, e.g. ALICE")
    amount: int = Field(..., gt=0, description="Fiat amount in cents")
    idempotency_key: str = Field("", description="Overrides Idempotency-Key header if provided")


class MintRequest(BaseModel):
    client_id: str = Field(..., description="Client whose reserved fiat is tokenized")
    amount: int = Field(..., gt=0, description="Token amount in cents (1:1 with reserved fiat)")
    idempotency_key: str = Field("", description="Overrides Idempotency-Key header if provided")


class TransferRequest(BaseModel):
    from_client_id: str = Field(..., description="Sender, e.g. ALICE")
    to_client_id: str = Field(..., description="Receiver, e.g. BOB")
    amount: int = Field(..., gt=0, description="Token amount in cents")
    idempotency_key: str = Field("", description="Overrides Idempotency-Key header if provided")


class RedeemRequest(BaseModel):
    client_id: str = Field(..., description="Client redeeming tokens to fiat")
    amount: int = Field(..., gt=0, description="Token amount to burn and credit as fiat")
    idempotency_key: str = Field("", description="Overrides Idempotency-Key header if provided")


class FiatAccountState(BaseModel):
    client_id: str
    available: int
    reserved: int


class TokenAccountState(BaseModel):
    client_id: str
    onchain_address: str
    balance: int


class BlockchainEvidence(BaseModel):
    transaction_hash: str | None = None
    block_number: int | None = None
    gas_used: int | None = None
    event_logs: list[dict[str, Any]] = Field(default_factory=list)


class LedgerSnapshot(BaseModel):
    fiat_ledger: list[FiatAccountState]
    token_ledger: list[TokenAccountState]


class OperationResponse(BaseModel):
    operation: str
    status: str
    message: str
    ledger: LedgerSnapshot
    blockchain: BlockchainEvidence
    institutional_notes: dict[str, str] = Field(default_factory=dict)
    transaction_record: TransactionRecord | None = None
