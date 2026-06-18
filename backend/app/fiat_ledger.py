"""
Off-chain fiat treasury ledger with transaction registry for Saga idempotency.

This is the bank's internal accounting book. It tracks real money (fiat) that exists
in the bank's systems — NOT on the blockchain. In real banking, this would be the
core banking system or general ledger that holds customer deposits.

Institutional parallel:
- Core banking / general ledger holds real money
- Kinexys/Citi/Partior never put fiat ON the blockchain — only token claims
"""

from dataclasses import dataclass, field

from backend.app.models import FiatAccountState, TransactionRecord, TransactionStatus


# A single customer's fiat account at the bank.
# "available" is money you can use or withdraw.
# "reserved" is money that's been set aside to be converted into digital tokens.
@dataclass
class FiatAccount:
    client_id: str
    available: int = 0   # Money that's free to use (like a checking account balance)
    reserved: int = 0    # Money that's been earmarked for tokenization


# The bank's ledger that tracks all customer fiat balances and transaction history.
# This is like the bank's database of who has how much money.
class FiatLedger:
    def __init__(self) -> None:
        # Set up the initial accounts: Alice starts with $1,000.00, Bob starts with $0.
        # All amounts are in cents (100,000 cents = $1,000.00).
        self._accounts: dict[str, FiatAccount] = {
            "ALICE": FiatAccount(client_id="ALICE", available=100_000, reserved=0),
            "BOB": FiatAccount(client_id="BOB", available=0, reserved=0),
        }
        # A log of every event that happened (like an audit trail).
        self._history: list[dict] = []
        # A registry of transactions keyed by their unique ID (for idempotency).
        self._transactions: dict[str, TransactionRecord] = {}

    # Take a picture of everyone's fiat balances at this moment.
    def snapshot(self) -> list[FiatAccountState]:
        return [
            FiatAccountState(
                client_id=a.client_id,
                available=a.available,
                reserved=a.reserved,
            )
            for a in self._accounts.values()
        ]

    # Find a customer's account by their name (case-insensitive).
    # Raises an error if the customer doesn't exist.
    def get(self, client_id: str) -> FiatAccount:
        key = client_id.upper()
        if key not in self._accounts:
            raise KeyError(f"Unknown client: {client_id}")
        return self._accounts[key]

    # Set money aside from a customer's available balance.
    # Like the bank putting a hold on funds when you want to convert them to tokens.
    def reserve(self, client_id: str, amount: int) -> None:
        acct = self.get(client_id)
        if acct.available < amount:
            raise ValueError(
                f"Insufficient available fiat for {client_id}: "
                f"available={acct.available}, requested={amount}"
            )
        acct.available -= amount   # Take money from available
        acct.reserved += amount    # And mark it as reserved
        self._record("RESERVE", client_id, amount)

    # Undo a reservation — move reserved money back to available.
    # This is a "compensation" action used when something goes wrong later in the process.
    def unreserve(self, client_id: str, amount: int) -> None:
        acct = self.get(client_id)
        if acct.reserved < amount:
            raise ValueError(
                f"Insufficient reserved fiat to unreserve for {client_id}: "
                f"reserved={acct.reserved}, requested={amount}"
            )
        acct.reserved -= amount    # Release the hold
        acct.available += amount   # Money is available again
        self._record("UNRESERVE", client_id, amount)

    # After tokens are successfully created on the blockchain, permanently remove the reserved money.
    # The bank keeps this money — it's now represented by digital tokens instead.
    def consume_reserved_for_mint(self, client_id: str, amount: int) -> None:
        acct = self.get(client_id)
        if acct.reserved < amount:
            raise ValueError(f"Insufficient reserved fiat for {client_id}")
        acct.reserved -= amount   # Remove the reserved money (it's now tokenized)
        self._record("CONSUME_RESERVED_FOR_MINT", client_id, amount)

    # Add money to a customer's available balance.
    # Used when someone redeems tokens back to cash — the bank adds the fiat back.
    def credit_available(self, client_id: str, amount: int) -> None:
        acct = self.get(client_id)
        acct.available += amount
        self._record("CREDIT_AVAILABLE", client_id, amount)

    # Remove money from a customer's available balance (reverse of credit).
    # A compensation action used when the redeem process fails after crediting.
    def debit_available(self, client_id: str, amount: int) -> None:
        acct = self.get(client_id)
        if acct.available < amount:
            raise ValueError(
                f"Insufficient available fiat to debit for {client_id}: "
                f"available={acct.available}, requested={amount}"
            )
        acct.available -= amount
        self._record("DEBIT_AVAILABLE", client_id, amount)

    # Save a transaction record so we can look it up later (for idempotency).
    def register_transaction(self, record: TransactionRecord) -> None:
        self._transactions[record.idempotency_key] = record

    # Look up a previous transaction by its unique key.
    def get_transaction(self, idempotency_key: str) -> TransactionRecord | None:
        return self._transactions.get(idempotency_key)

    # Update the status of an existing transaction (e.g., from PENDING to COMPLETED).
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

    # Log an event (internal helper for the audit trail).
    def _record(self, event: str, client_id: str, amount: int) -> None:
        self._history.append(
            {
                "event": event,
                "client_id": client_id.upper(),
                "amount": amount,
                "snapshot": self.snapshot(),
            }
        )

    # Get the full history of events (read-only, like an audit log).
    @property
    def history(self) -> list[dict]:
        return list(self._history)
