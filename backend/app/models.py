"""Request/response schemas and transaction state models for settlement API.

This file defines the "shapes" of data that flow in and out of our API.
Think of it like a form template — it describes what information each request
must include and what each response will look like.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# The possible states a transaction can be in — like tracking a package's delivery status.
class TransactionStatus(str, Enum):
    PENDING = "PENDING"                    # Just created, not yet started
    RESERVED = "RESERVED"                  # Fiat money has been set aside
    ONCHAIN_SUBMITTED = "ONCHAIN_SUBMITTED" # Sent to the blockchain, waiting for confirmation
    COMPLETED = "COMPLETED"                # Successfully finished
    FAILED = "FAILED"                      # Something went wrong


# A record of everything that happened during a transaction — like a bank statement entry.
class TransactionRecord(BaseModel):
    idempotency_key: str         # Unique ID to prevent double-processing
    operation_type: str          # What kind of operation (reserve, mint, transfer, redeem)
    status: TransactionStatus    # Current status of this transaction
    client_id: str | None = None      # Who initiated this
    to_client_id: str | None = None   # Who received (for transfers)
    amount: int = 0                   # Amount in cents
    created_at: datetime = Field(default_factory=datetime.utcnow)   # When it started
    updated_at: datetime = Field(default_factory=datetime.utcnow)   # When it was last changed
    error_message: str | None = None  # What went wrong, if anything


# The information needed to reserve fiat money (like a withdrawal slip).
class ReserveRequest(BaseModel):
    client_id: str = Field(..., description="Institutional client, e.g. ALICE")
    amount: int = Field(..., gt=0, description="Fiat amount in cents")
    idempotency_key: str = Field("", description="Overrides Idempotency-Key header if provided")


# The information needed to mint (create) deposit tokens.
class MintRequest(BaseModel):
    client_id: str = Field(..., description="Client whose reserved fiat is tokenized")
    amount: int = Field(..., gt=0, description="Token amount in cents (1:1 with reserved fiat)")
    idempotency_key: str = Field("", description="Overrides Idempotency-Key header if provided")


# The information needed to transfer tokens from one person to another.
class TransferRequest(BaseModel):
    from_client_id: str = Field(..., description="Sender, e.g. ALICE")
    to_client_id: str = Field(..., description="Receiver, e.g. BOB")
    amount: int = Field(..., gt=0, description="Token amount in cents")
    idempotency_key: str = Field("", description="Overrides Idempotency-Key header if provided")


# The information needed to redeem (cash out) tokens back to real money.
class RedeemRequest(BaseModel):
    client_id: str = Field(..., description="Client redeeming tokens to fiat")
    amount: int = Field(..., gt=0, description="Token amount to burn and credit as fiat")
    idempotency_key: str = Field("", description="Overrides Idempotency-Key header if provided")


# A snapshot of a customer's fiat (real money) account — how much they have and how much is set aside.
class FiatAccountState(BaseModel):
    client_id: str
    available: int     # Money you can use right now
    reserved: int      # Money set aside for tokenization


# A snapshot of a customer's token balance on the blockchain.
class TokenAccountState(BaseModel):
    client_id: str
    onchain_address: str  # Their blockchain account address
    balance: int          # How many tokens they own


# Proof that something happened on the blockchain — like a receipt from a transaction.
class BlockchainEvidence(BaseModel):
    transaction_hash: str | None = None  # The blockchain transaction ID
    block_number: int | None = None      # Which block it was recorded in
    gas_used: int | None = None          # How much processing power it cost
    event_logs: list[dict[str, Any]] = Field(default_factory=list)  # Detailed event records


# A complete picture of everyone's money at a moment in time.
class LedgerSnapshot(BaseModel):
    fiat_ledger: list[FiatAccountState]   # Real money balances
    token_ledger: list[TokenAccountState] # Digital token balances


# The standard response format our API sends back for every operation.
# Like a detailed receipt that includes what happened, the new balances, and blockchain proof.
class OperationResponse(BaseModel):
    operation: str                                                    # What was done
    status: str                                                       # Success or failure
    message: str                                                      # Human-readable explanation
    ledger: LedgerSnapshot                                            # Current balances after the operation
    blockchain: BlockchainEvidence                                    # Proof from the blockchain
    institutional_notes: dict[str, str] = Field(default_factory=dict) # Extra context for bankers
    transaction_record: TransactionRecord | None = None               # Full audit trail
