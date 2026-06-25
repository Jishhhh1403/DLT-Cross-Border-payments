import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.db_models import Account, Wallet
from backend.app.fiat_ledger import FiatLedger
from backend.app.models import TransactionRecord, TransactionStatus


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()
    alice = Account(client_id="ALICE", available=100_000, reserved=0)
    bob = Account(client_id="BOB", available=0, reserved=0)
    db.add_all([alice, bob])
    db.commit()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def ledger(session):
    return FiatLedger(session)


class TestFiatLedger:
    def test_initial_state(self, ledger: FiatLedger):
        snap = ledger.snapshot()
        assert len(snap) == 2
        alice = next(a for a in snap if a.client_id == "ALICE")
        assert alice.available == 100_000
        assert alice.reserved == 0

    def test_reserve_success(self, ledger: FiatLedger):
        ledger.reserve("ALICE", 10_000)
        acct = ledger.get("ALICE")
        assert acct.available == 90_000
        assert acct.reserved == 10_000

    def test_reserve_insufficient(self, ledger: FiatLedger):
        with pytest.raises(ValueError, match="Insufficient"):
            ledger.reserve("ALICE", 999_999)

    def test_unreserve_compensation(self, ledger: FiatLedger):
        ledger.reserve("ALICE", 10_000)
        ledger.unreserve("ALICE", 5_000)
        acct = ledger.get("ALICE")
        assert acct.available == 95_000
        assert acct.reserved == 5_000

    def test_unreserve_excess(self, ledger: FiatLedger):
        with pytest.raises(ValueError, match="Insufficient reserved"):
            ledger.unreserve("ALICE", 999_999)

    def test_consume_reserved_for_mint(self, ledger: FiatLedger):
        ledger.reserve("ALICE", 10_000)
        ledger.consume_reserved_for_mint("ALICE", 10_000)
        acct = ledger.get("ALICE")
        assert acct.available == 90_000
        assert acct.reserved == 0

    def test_credit_available(self, ledger: FiatLedger):
        ledger.credit_available("BOB", 5_000)
        acct = ledger.get("BOB")
        assert acct.available == 5_000

    def test_debit_available_compensation(self, ledger: FiatLedger):
        ledger.credit_available("BOB", 5_000)
        ledger.debit_available("BOB", 3_000)
        acct = ledger.get("BOB")
        assert acct.available == 2_000

    def test_debit_available_excess(self, ledger: FiatLedger):
        with pytest.raises(ValueError, match="Insufficient available"):
            ledger.debit_available("BOB", 999_999)

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

        ledger.update_transaction_status("test-key-1", TransactionStatus.COMPLETED)
        retrieved = ledger.get_transaction("test-key-1")
        assert retrieved.status == TransactionStatus.COMPLETED

    def test_transaction_registry_missing(self, ledger: FiatLedger):
        assert ledger.get_transaction("nonexistent") is None

    def test_audit_log(self, ledger: FiatLedger):
        ledger.reserve("ALICE", 1_000)
        ledger.unreserve("ALICE", 500)
        from backend.app.db_models import AuditLog
        entries = ledger.session.query(AuditLog).all()
        assert len(entries) == 2
        assert entries[0].event == "RESERVE"
        assert entries[1].event == "UNRESERVE"

    def test_unknown_client(self, ledger: FiatLedger):
        with pytest.raises(KeyError):
            ledger.get("UNKNOWN")
