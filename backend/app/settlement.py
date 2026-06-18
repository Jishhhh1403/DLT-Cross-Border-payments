"""
Payment orchestration — coordinates off-chain fiat ledger with on-chain token operations
via a Saga pattern for atomic settlement.

This is the brain of the system. It orchestrates each payment step by coordinating
the bank's internal ledger (fiat) with the blockchain (tokens). If something fails,
it uses "compensation" actions to undo previous steps — like a safety net that
ensures money never gets lost.

Institutional parallels:
- Kinexys, Citi Token Services, Partior implement this between core banking and ledger.
"""

from datetime import datetime

from backend.app.blockchain.client import BesuClient
from backend.app.fiat_ledger import FiatLedger
from backend.app.models import (
    BlockchainEvidence,
    LedgerSnapshot,
    MintRequest,
    OperationResponse,
    RedeemRequest,
    ReserveRequest,
    TokenAccountState,
    TransactionRecord,
    TransactionStatus,
    TransferRequest,
)

# Reference notes about how real-world banks do this — useful context for bankers reading the output.
INSTITUTIONAL_NOTES = {
    "kinexys": (
        "JPM Kinexys: fiat movement is booked in JPM treasury; deposit tokens are minted "
        "on the permissioned network only after funds are earmarked. Transfer is atomic on-ledger."
    ),
    "citi_token_services": (
        "Citi Token Services: Citi holds fiat; mint creates Citi-issued deposit tokens. "
        "Redemption burns tokens and releases fiat from tokenized pool to beneficiary account."
    ),
    "partior": (
        "Partior: multi-bank shared ledger; token transfer updates ownership while "
        "nostro positions are net-settled between member banks off-ledger or via RTGS."
    ),
}


# The orchestrator that coordinates the entire settlement lifecycle.
# It knows how to talk to both the fiat ledger and the blockchain.
class SettlementOrchestrator:
    def __init__(self, fiat: FiatLedger, chain: BesuClient) -> None:
        self.fiat = fiat    # The bank's internal ledger (real money)
        self.chain = chain  # The blockchain connection (digital tokens)

    # Take a snapshot of everyone's token balances on the blockchain.
    def _token_snapshot(self) -> list[TokenAccountState]:
        return [
            TokenAccountState(
                client_id="ALICE",
                onchain_address=self.chain.client_addresses["ALICE"],
                balance=self.chain.token_balance("ALICE"),
            ),
            TokenAccountState(
                client_id="BOB",
                onchain_address=self.chain.client_addresses["BOB"],
                balance=self.chain.token_balance("BOB"),
            ),
        ]

    # Take a complete picture of both fiat and token balances.
    def _ledger_snapshot(self) -> LedgerSnapshot:
        return LedgerSnapshot(
            fiat_ledger=self.fiat.snapshot(),
            token_ledger=self._token_snapshot(),
        )

    # Build the standard response format that includes the result, balances, and blockchain proof.
    def _response(
        self,
        operation: str,
        status: str,
        message: str,
        receipt=None,
        transaction_record: TransactionRecord | None = None,
    ) -> OperationResponse:
        evidence = BlockchainEvidence(**self.chain.receipt_to_evidence(receipt))
        return OperationResponse(
            operation=operation,
            status=status,
            message=message,
            ledger=self._ledger_snapshot(),
            blockchain=evidence,
            institutional_notes=INSTITUTIONAL_NOTES,
            transaction_record=transaction_record,
        )

    # Create a new transaction record in the fiat ledger's registry.
    # This is used for tracking and preventing duplicate processing.
    def _create_record(
        self,
        key: str,
        operation: str,
        client_id: str | None = None,
        to_client_id: str | None = None,
        amount: int = 0,
    ) -> TransactionRecord:
        record = TransactionRecord(
            idempotency_key=key,
            operation_type=operation,
            status=TransactionStatus.PENDING,
            client_id=client_id,
            to_client_id=to_client_id,
            amount=amount,
        )
        self.fiat.register_transaction(record)
        return record

    # Update the status of an existing transaction in the registry.
    def _update_status(
        self,
        key: str,
        status: TransactionStatus,
        error: str | None = None,
    ) -> None:
        self.fiat.update_transaction_status(key, status, error)

    # Look up a previously recorded transaction by its unique key.
    def _get_record(self, key: str) -> TransactionRecord | None:
        return self.fiat.get_transaction(key)

    # Step 1: Reserve fiat money.
    # Sets aside money in the bank's ledger for tokenization.
    # No blockchain involved — purely a bank accounting operation.
    def reserve(self, req: ReserveRequest) -> OperationResponse:
        existing = self._get_record(req.idempotency_key)
        if existing is not None and existing.status == TransactionStatus.COMPLETED:
            return self._response("RESERVE", "success", "Idempotent replay — already reserved", transaction_record=existing)

        record = self._create_record(req.idempotency_key, "RESERVE", client_id=req.client_id, amount=req.amount)
        try:
            self.fiat.reserve(req.client_id, req.amount)
            self._update_status(req.idempotency_key, TransactionStatus.COMPLETED)
            record.status = TransactionStatus.COMPLETED
            return self._response(
                operation="RESERVE",
                status="success",
                message=(
                    f"Reserved {req.amount} cents fiat for {req.client_id.upper()}. "
                    "No blockchain transaction — treasury ledger update only."
                ),
                receipt=None,
                transaction_record=record,
            )
        except ValueError as e:
            self._update_status(req.idempotency_key, TransactionStatus.FAILED, str(e))
            record.status = TransactionStatus.FAILED
            record.error_message = str(e)
            raise

    # Step 2: Mint deposit tokens on the blockchain.
    # This converts reserved fiat into digital tokens using a "Saga" pattern — if any step fails,
    # previous steps are undone (compensated) to keep everything consistent.
    def mint(self, req: MintRequest) -> OperationResponse:
        existing = self._get_record(req.idempotency_key)
        if existing is not None and existing.status == TransactionStatus.COMPLETED:
            return self._response("MINT", "success", "Idempotent replay — already minted", transaction_record=existing)

        record = self._create_record(req.idempotency_key, "MINT", client_id=req.client_id, amount=req.amount)

        try:
            acct = self.fiat.get(req.client_id)
            if acct.reserved < req.amount:
                raise ValueError(
                    f"Mint requires reserved fiat: {req.client_id} reserved={acct.reserved}, "
                    f"requested={req.amount}. Call /reserve first."
                )

            self._update_status(req.idempotency_key, TransactionStatus.RESERVED)
            record.status = TransactionStatus.RESERVED

            # Attempt to create tokens on the blockchain.
            try:
                receipt = self.chain.mint_tokens(req.client_id, req.amount)
            except Exception as e:
                # Blockchain mint failed — undo the reservation (compensation).
                self.fiat.unreserve(req.client_id, req.amount)
                self._update_status(req.idempotency_key, TransactionStatus.FAILED, f"On-chain mint failed, fiat unreserved: {e}")
                record.status = TransactionStatus.FAILED
                record.error_message = str(e)
                return self._response(
                    operation="MINT",
                    status="failed",
                    message=f"Mint failed, compensating transaction executed (fiat unreserved): {e}",
                    receipt=None,
                    transaction_record=record,
                )

            self._update_status(req.idempotency_key, TransactionStatus.ONCHAIN_SUBMITTED)
            record.status = TransactionStatus.ONCHAIN_SUBMITTED

            # Tokens created — now finalize by consuming the reserved fiat.
            try:
                self.fiat.consume_reserved_for_mint(req.client_id, req.amount)
            except Exception as e:
                # Fiat consumption failed — undo both: unreserve fiat AND burn the newly created tokens.
                # This is a "dual compensation" (undo two things).
                self.fiat.unreserve(req.client_id, req.amount)
                self.chain.burn_tokens(req.client_id, req.amount)
                self._update_status(req.idempotency_key, TransactionStatus.FAILED, f"Fiat consumption failed, dual compensation: {e}")
                record.status = TransactionStatus.FAILED
                record.error_message = str(e)
                return self._response(
                    operation="MINT",
                    status="failed",
                    message=f"Mint failed during fiat finalization, dual compensation executed: {e}",
                    receipt=receipt,
                    transaction_record=record,
                )

            self._update_status(req.idempotency_key, TransactionStatus.COMPLETED)
            record.status = TransactionStatus.COMPLETED
            return self._response(
                operation="MINT",
                status="success",
                message=(
                    f"Minted {req.amount} deposit tokens to {req.client_id.upper()} on-ledger. "
                    f"totalSupply on-chain = {self.chain.total_supply()}"
                ),
                receipt=receipt,
                transaction_record=record,
            )

        except ValueError as e:
            self._update_status(req.idempotency_key, TransactionStatus.FAILED, str(e))
            record.status = TransactionStatus.FAILED
            record.error_message = str(e)
            raise

    # Step 3: Transfer tokens from one person to another on the blockchain.
    # This is a pure blockchain operation — the fiat ledger is not involved.
    def transfer(self, req: TransferRequest) -> OperationResponse:
        existing = self._get_record(req.idempotency_key)
        if existing is not None and existing.status == TransactionStatus.COMPLETED:
            return self._response("TRANSFER", "success", "Idempotent replay — already transferred", transaction_record=existing)

        record = self._create_record(
            req.idempotency_key, "TRANSFER",
            client_id=req.from_client_id, to_client_id=req.to_client_id, amount=req.amount,
        )

        try:
            receipt = self.chain.transfer_tokens(req.from_client_id, req.to_client_id, req.amount)
        except Exception as e:
            self._update_status(req.idempotency_key, TransactionStatus.FAILED, str(e))
            record.status = TransactionStatus.FAILED
            record.error_message = str(e)
            return self._response(
                operation="TRANSFER",
                status="failed",
                message=f"Transfer failed: {e}",
                receipt=None,
                transaction_record=record,
            )

        self._update_status(req.idempotency_key, TransactionStatus.COMPLETED)
        record.status = TransactionStatus.COMPLETED
        return self._response(
            operation="TRANSFER",
            status="success",
            message=(
                f"Transferred {req.amount} tokens from {req.from_client_id.upper()} "
                f"to {req.to_client_id.upper()} on-ledger."
            ),
            receipt=receipt,
            transaction_record=record,
        )

    # Step 4: Redeem tokens back to real money.
    # Burns the tokens on the blockchain and credits the customer's fiat account.
    # If the fiat credit fails, the tokens are minted back (compensation).
    def redeem(self, req: RedeemRequest) -> OperationResponse:
        existing = self._get_record(req.idempotency_key)
        if existing is not None and existing.status == TransactionStatus.COMPLETED:
            return self._response("REDEEM", "success", "Idempotent replay — already redeemed", transaction_record=existing)

        record = self._create_record(req.idempotency_key, "REDEEM", client_id=req.client_id, amount=req.amount)

        try:
            # First, destroy the tokens on the blockchain.
            receipt = self.chain.burn_tokens(req.client_id, req.amount)
        except Exception as e:
            self._update_status(req.idempotency_key, TransactionStatus.FAILED, str(e))
            record.status = TransactionStatus.FAILED
            record.error_message = str(e)
            return self._response(
                operation="REDEEM",
                status="failed",
                message=f"On-chain burn failed: {e}",
                receipt=None,
                transaction_record=record,
            )

        self._update_status(req.idempotency_key, TransactionStatus.ONCHAIN_SUBMITTED)
        record.status = TransactionStatus.ONCHAIN_SUBMITTED

        # Then, credit the customer's fiat account.
        try:
            self.fiat.credit_available(req.client_id, req.amount)
        except Exception as e:
            # Fiat credit failed — undo by minting the tokens back (compensation).
            self.chain.mint_tokens(req.client_id, req.amount)
            self._update_status(req.idempotency_key, TransactionStatus.FAILED, f"Fiat credit failed, token minted back: {e}")
            record.status = TransactionStatus.FAILED
            record.error_message = str(e)
            return self._response(
                operation="REDEEM",
                status="failed",
                message=f"Redeem failed during fiat credit, compensating mint executed: {e}",
                receipt=receipt,
                transaction_record=record,
            )

        self._update_status(req.idempotency_key, TransactionStatus.COMPLETED)
        record.status = TransactionStatus.COMPLETED
        return self._response(
            operation="REDEEM",
            status="success",
            message=(
                f"Burned {req.amount} tokens and credited {req.amount} cents fiat "
                f"to {req.client_id.upper()} available balance."
            ),
            receipt=receipt,
            transaction_record=record,
        )

    # Get a complete snapshot of all balances (both fiat and tokens).
    def balances(self) -> OperationResponse:
        return self._response(
            operation="BALANCES",
            status="success",
            message="Current fiat and token ledger snapshot.",
            receipt=None,
        )
