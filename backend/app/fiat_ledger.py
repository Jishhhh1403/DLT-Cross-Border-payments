"""
Off-chain fiat treasury ledger with PostgreSQL persistence.

This class now uses SQLAlchemy to interact with a PostgreSQL database.
It uses SELECT FOR UPDATE (with_for_update) to ensure that account balances
are locked during a transaction, preventing race conditions and double-spending.
"""

import json
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.app.db_models import Account, Transaction, AuditLog
from backend.app.models import FiatAccountState, TransactionRecord, TransactionStatus


class FiatLedger:
    def __init__(self, session: Session):
        # We now receive a database session instead of managing state internally.
        self.session = session

    def snapshot(self) -> list[FiatAccountState]:
        # Read all accounts from the database.
        accounts = self.session.execute(select(Account)).scalars().all()
        return [
            FiatAccountState(
                client_id=a.client_id,
                available=a.available,
                reserved=a.reserved,
            )
            for a in accounts
        ]

    def get(self, client_id: str, lock: bool = False) -> Account:
        # Look up a customer account.
        # If lock=True, we use SELECT FOR UPDATE to lock the row in the DB.
        key = client_id.upper()
        stmt = select(Account).where(Account.client_id == key)
        if lock:
            stmt = stmt.with_for_update()
        
        account = self.session.execute(stmt).scalar_one_or_none()
        if account is None:
            raise KeyError(f"Unknown client: {client_id}")
        return account

    def reserve(self, client_id: str, amount: int) -> None:
        # Lock the account row to prevent concurrent modifications.
        acct = self.get(client_id, lock=True)
        if acct.available < amount:
            raise ValueError(
                f"Insufficient available fiat for {client_id}: "
                f"available={acct.available}, requested={amount}"
            )
        acct.available -= amount
        acct.reserved += amount
        self._record("RESERVE", client_id, amount)

    def unreserve(self, client_id: str, amount: int) -> None:
        acct = self.get(client_id, lock=True)
        if acct.reserved < amount:
            raise ValueError(
                f"Insufficient reserved fiat to unreserve for {client_id}: "
                f"reserved={acct.reserved}, requested={amount}"
            )
        acct.reserved -= amount
        acct.available += amount
        self._record("UNRESERVE", client_id, amount)

    def consume_reserved_for_mint(self, client_id: str, amount: int) -> None:
        acct = self.get(client_id, lock=True)
        if acct.reserved < amount:
            raise ValueError(f"Insufficient reserved fiat for {client_id}")
        acct.reserved -= amount
        self._record("CONSUME_RESERVED_FOR_MINT", client_id, amount)

    def credit_available(self, client_id: str, amount: int) -> None:
        acct = self.get(client_id, lock=True)
        acct.available += amount
        self._record("CREDIT_AVAILABLE", client_id, amount)

    def debit_available(self, client_id: str, amount: int) -> None:
        acct = self.get(client_id, lock=True)
        if acct.available < amount:
            raise ValueError(
                f"Insufficient available fiat to debit for {client_id}: "
                f"available={acct.available}, requested={amount}"
            )
        acct.available -= amount
        self._record("DEBIT_AVAILABLE", client_id, amount)

    def register_transaction(self, record: TransactionRecord) -> None:
        # Convert the Pydantic model to a SQLAlchemy model.
        db_record = Transaction(
            idempotency_key=record.idempotency_key,
            operation_type=record.operation_type,
            status=record.status,
            client_id=record.client_id,
            to_client_id=record.to_client_id,
            amount=record.amount,
            error_message=record.error_message,
        )
        self.session.add(db_record)
        # Flush to ensure it's in the DB but not yet committed.
        self.session.flush()

    def get_transaction(self, idempotency_key: str) -> TransactionRecord | None:
        # Retrieve transaction and convert back to Pydantic model for the orchestrator.
        db_tx = self.session.get(Transaction, idempotency_key)
        if db_tx is None:
            return None
        return TransactionRecord(
            idempotency_key=db_tx.idempotency_key,
            operation_type=db_tx.operation_type,
            status=db_tx.status,
            client_id=db_tx.client_id,
            to_client_id=db_tx.to_client_id,
            amount=db_tx.amount,
            error_message=db_tx.error_message,
        )

    def update_transaction_status(
        self,
        idempotency_key: str,
        status: TransactionStatus,
        error_message: str | None = None,
    ) -> None:
        db_tx = self.session.get(Transaction, idempotency_key)
        if db_tx is not None:
            db_tx.status = status
            if error_message is not None:
                db_tx.error_message = error_message

    def _record(self, event: str, client_id: str, amount: int) -> None:
        # Log to the AuditLog table.
        # We take a snapshot of current accounts to store as JSON for the audit trail.
        snapshot = self.snapshot()
        snap_json = json.dumps([a.model_dump() for a in snapshot])
        
        log = AuditLog(
            event=event,
            client_id=client_id.upper(),
            amount=amount,
            snapshot_json=snap_json,
        )
        self.session.add(log)
