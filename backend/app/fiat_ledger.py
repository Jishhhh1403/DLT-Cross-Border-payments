"""
Off-chain fiat treasury ledger with transaction registry for Saga idempotency.

Institutional parallel:
- Core banking / general ledger holds real money
- Kinexys/Citi/Partior never put fiat ON the blockchain — only token claims
"""

from dataclasses import dataclass, field

from backend.app.models import FiatAccountState, TransactionRecord, TransactionStatus


@dataclass
class FiatAccount:
    client_id: str
    available: int = 0
    reserved: int = 0


class FiatLedger:
    """Simulates bank treasury balances with available vs reserved buckets and transaction registry."""

    def __init__(self) -> None:
        self._accounts: dict[str, FiatAccount] = {
            "ALICE": FiatAccount(client_id="ALICE", available=100_000, reserved=0),
            "BOB": FiatAccount(client_id="BOB", available=0, reserved=0),
        }
        self._history: list[dict] = []
        self._transactions: dict[str, TransactionRecord] = {}

    def snapshot(self) -> list[FiatAccountState]:
        return [
            FiatAccountState(
                client_id=a.client_id,
                available=a.available,
                reserved=a.reserved,
            )
            for a in self._accounts.values()
        ]

    def get(self, client_id: str) -> FiatAccount:
        key = client_id.upper()
        if key not in self._accounts:
            raise KeyError(f"Unknown client: {client_id}")
        return self._accounts[key]

    def reserve(self, client_id: str, amount: int) -> None:
        acct = self.get(client_id)
        if acct.available < amount:
            raise ValueError(
                f"Insufficient available fiat for {client_id}: "
                f"available={acct.available}, requested={amount}"
            )
        acct.available -= amount
        acct.reserved += amount
        self._record("RESERVE", client_id, amount)

    def unreserve(self, client_id: str, amount: int) -> None:
        """Compensation: move reserved fiat back to available."""
        acct = self.get(client_id)
        if acct.reserved < amount:
            raise ValueError(
                f"Insufficient reserved fiat to unreserve for {client_id}: "
                f"reserved={acct.reserved}, requested={amount}"
            )
        acct.reserved -= amount
        acct.available += amount
        self._record("UNRESERVE", client_id, amount)

    def consume_reserved_for_mint(self, client_id: str, amount: int) -> None:
        """After successful mint, reserved fiat is consumed (still at bank, now tokenized)."""
        acct = self.get(client_id)
        if acct.reserved < amount:
            raise ValueError(f"Insufficient reserved fiat for {client_id}")
        acct.reserved -= amount
        self._record("CONSUME_RESERVED_FOR_MINT", client_id, amount)

    def credit_available(self, client_id: str, amount: int) -> None:
        acct = self.get(client_id)
        acct.available += amount
        self._record("CREDIT_AVAILABLE", client_id, amount)

    def debit_available(self, client_id: str, amount: int) -> None:
        """Compensation: reverse a credit_available."""
        acct = self.get(client_id)
        if acct.available < amount:
            raise ValueError(
                f"Insufficient available fiat to debit for {client_id}: "
                f"available={acct.available}, requested={amount}"
            )
        acct.available -= amount
        self._record("DEBIT_AVAILABLE", client_id, amount)

    def register_transaction(self, record: TransactionRecord) -> None:
        self._transactions[record.idempotency_key] = record

    def get_transaction(self, idempotency_key: str) -> TransactionRecord | None:
        return self._transactions.get(idempotency_key)

    def update_transaction_status(
        self,
        idempotency_key: str,
        status: TransactionStatus,
        error_message: str | None = None,
    ) -> None:
        record = self._transactions.get(idempotency_key)
        if record is not None:
            record.status = status
            record.updated_at = __import__("datetime").datetime.utcnow()
            if error_message is not None:
                record.error_message = error_message

    def _record(self, event: str, client_id: str, amount: int) -> None:
        self._history.append(
            {
                "event": event,
                "client_id": client_id.upper(),
                "amount": amount,
                "snapshot": self.snapshot(),
            }
        )

    @property
    def history(self) -> list[dict]:
        return list(self._history)
