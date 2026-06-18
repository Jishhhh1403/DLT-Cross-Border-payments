"""
Tests for the FiatLedger — the bank's internal accounting system.

These tests check that the fiat ledger correctly handles:
- Reserving money (setting funds aside)
- Unreserving money (undoing a reservation)
- Consuming reserved money for token minting
- Crediting and debiting available balances
- Tracking transactions by their unique key
- Maintaining an audit history
"""

import pytest

from backend.app.fiat_ledger import FiatLedger
from backend.app.models import TransactionRecord, TransactionStatus


# Create a fresh ledger before each test (so tests don't interfere with each other).
@pytest.fixture
def ledger():
    return FiatLedger()


# All tests for the fiat ledger's core functionality.
class TestFiatLedger:
    # Verify the initial setup: Alice has $1,000, Bob has $0, nothing is reserved.
    def test_initial_state(self, ledger: FiatLedger):
        snap = ledger.snapshot()
        assert len(snap) == 2
        alice = next(a for a in snap if a.client_id == "ALICE")
        assert alice.available == 100_000
        assert alice.reserved == 0

    # Successfully reserve $100 from Alice's account.
    def test_reserve_success(self, ledger: FiatLedger):
        ledger.reserve("ALICE", 10_000)
        acct = ledger.get("ALICE")
        assert acct.available == 90_000
        assert acct.reserved == 10_000

    # Try to reserve more money than Alice has (should fail).
    def test_reserve_insufficient(self, ledger: FiatLedger):
        with pytest.raises(ValueError, match="Insufficient"):
            ledger.reserve("ALICE", 999_999)

    # Test the compensation action: unreserving (undoing a reservation).
    def test_unreserve_compensation(self, ledger: FiatLedger):
        ledger.reserve("ALICE", 10_000)
        ledger.unreserve("ALICE", 5_000)
        acct = ledger.get("ALICE")
        assert acct.available == 95_000
        assert acct.reserved == 5_000

    # Try to unreserve more than was reserved (should fail).
    def test_unreserve_excess(self, ledger: FiatLedger):
        with pytest.raises(ValueError, match="Insufficient reserved"):
            ledger.unreserve("ALICE", 999_999)

    # Test that consuming reserved money for minting works correctly.
    def test_consume_reserved_for_mint(self, ledger: FiatLedger):
        ledger.reserve("ALICE", 10_000)
        ledger.consume_reserved_for_mint("ALICE", 10_000)
        acct = ledger.get("ALICE")
        assert acct.available == 90_000
        assert acct.reserved == 0

    # Test adding money to a customer's available balance (credit).
    def test_credit_available(self, ledger: FiatLedger):
        ledger.credit_available("BOB", 5_000)
        acct = ledger.get("BOB")
        assert acct.available == 5_000

    # Test the compensation action: debiting (undoing a credit).
    def test_debit_available_compensation(self, ledger: FiatLedger):
        ledger.credit_available("BOB", 5_000)
        ledger.debit_available("BOB", 3_000)
        acct = ledger.get("BOB")
        assert acct.available == 2_000

    # Try to debit more than the available balance (should fail).
    def test_debit_available_excess(self, ledger: FiatLedger):
        with pytest.raises(ValueError, match="Insufficient available"):
            ledger.debit_available("BOB", 999_999)

    # Test the transaction registry: saving and looking up transactions by key.
    def test_transaction_registry(self, ledger: FiatLedger):
        record = TransactionRecord(
            idempotency_key="test-key-1",
            operation_type="MINT",
            status=TransactionStatus.PENDING,
            client_id="ALICE",
            amount=1000,
        )
        ledger.register_transaction(record)
        retrieved = ledger.get_transaction("test-key-1")
        assert retrieved is not None
        assert retrieved.status == TransactionStatus.PENDING

        # Update the status and verify it changed.
        ledger.update_transaction_status("test-key-1", TransactionStatus.COMPLETED)
        retrieved = ledger.get_transaction("test-key-1")
        assert retrieved.status == TransactionStatus.COMPLETED

    # Looking up a non-existent transaction should return nothing.
    def test_transaction_registry_missing(self, ledger: FiatLedger):
        assert ledger.get_transaction("nonexistent") is None

    # Test that the audit history correctly records all events.
    def test_history_tracking(self, ledger: FiatLedger):
        ledger.reserve("ALICE", 1_000)
        ledger.unreserve("ALICE", 500)
        assert len(ledger.history) == 2
        assert ledger.history[0]["event"] == "RESERVE"
        assert ledger.history[1]["event"] == "UNRESERVE"

    # Looking up a client that doesn't exist should raise an error.
    def test_unknown_client(self, ledger: FiatLedger):
        with pytest.raises(KeyError):
            ledger.get("UNKNOWN")
