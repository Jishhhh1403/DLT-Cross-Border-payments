"""
Tests for the SettlementOrchestrator — the brain that coordinates payments.

These tests verify the full "Saga" pattern: each payment step (reserve, mint,
transfer, redeem) is tested for success, failure, and the ability to undo
(compensate) when something goes wrong. The blockchain is mocked (simulated)
so we can test without a real blockchain network.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from backend.app.fiat_ledger import FiatLedger
from backend.app.models import MintRequest, RedeemRequest, ReserveRequest, TransferRequest
from backend.app.settlement import SettlementOrchestrator


# Create a fake blockchain client that returns predictable results.
# This lets us test the orchestrator without needing a real blockchain connection.
def _make_mock_chain() -> MagicMock:
    chain = MagicMock()
    chain.client_addresses = {
        "ALICE": "0xALICE",
        "BOB": "0xBOB",
    }
    chain.token_balance.return_value = 0
    chain.total_supply.return_value = 0
    # Fake successful transaction receipts for mint, burn, and transfer.
    chain.mint_tokens.return_value = {
        "transactionHash": b"\x01",
        "blockNumber": 1,
        "gasUsed": 50000,
        "logs": [],
        "status": 1,
    }
    chain.burn_tokens.return_value = {
        "transactionHash": b"\x02",
        "blockNumber": 2,
        "gasUsed": 50000,
        "logs": [],
        "status": 1,
    }
    chain.transfer_tokens.return_value = {
        "transactionHash": b"\x03",
        "blockNumber": 3,
        "gasUsed": 50000,
        "logs": [],
        "status": 1,
    }
    chain.receipt_to_evidence.return_value = {
        "transaction_hash": "0x01",
        "block_number": 1,
        "gas_used": 50000,
        "event_logs": [],
    }
    return chain


# Set up the test environment: a fresh ledger and a mock blockchain for each test.
@pytest.fixture
def orch():
    ledger = FiatLedger()
    chain = _make_mock_chain()
    return SettlementOrchestrator(ledger, chain)


# Tests for the MINT operation — creating deposit tokens.
class TestSagaMint:
    # Full successful mint: reserve -> mint on blockchain -> consume reserved fiat.
    def test_mint_full_saga_success(self, orch: SettlementOrchestrator):
        orch.fiat.reserve("ALICE", 1000)
        key = str(uuid4())
        req = MintRequest(client_id="ALICE", amount=1000, idempotency_key=key)
        resp = orch.mint(req)
        assert resp.status == "success"
        acct = orch.fiat.get("ALICE")
        assert acct.reserved == 0
        assert acct.available == 99_000

    # Calling mint twice with the same key should return the same result (idempotency).
    def test_mint_idempotency(self, orch: SettlementOrchestrator):
        orch.fiat.reserve("ALICE", 1000)
        key = str(uuid4())
        req = MintRequest(client_id="ALICE", amount=1000, idempotency_key=key)
        resp1 = orch.mint(req)
        assert resp1.status == "success"
        resp2 = orch.mint(req)
        assert resp2.status == "success"
        assert "Idempotent" in resp2.message

    # Trying to mint without enough reserved fiat should fail.
    def test_mint_insufficient_reserved(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = MintRequest(client_id="ALICE", amount=999_999, idempotency_key=key)
        with pytest.raises(ValueError, match="reserved"):
            orch.mint(req)

    # If the blockchain mint fails, the reservation should be undone (compensation).
    def test_mint_onchain_failure_compensates(self, orch: SettlementOrchestrator):
        orch.fiat.reserve("ALICE", 1000)
        orch.chain.mint_tokens.side_effect = RuntimeError("Besu timeout")
        key = str(uuid4())
        req = MintRequest(client_id="ALICE", amount=1000, idempotency_key=key)
        resp = orch.mint(req)
        assert resp.status == "failed"
        assert "compensating" in resp.message.lower()
        acct = orch.fiat.get("ALICE")
        assert acct.reserved == 0
        assert acct.available == 100_000

    # If the fiat finalization fails after the blockchain mint succeeded,
    # both the blockchain mint AND the reservation should be undone (dual compensation).
    def test_mint_fiat_finalization_failure_dual_compensate(self, orch: SettlementOrchestrator):
        orch.fiat.reserve("ALICE", 1000)
        def failing_consume(client_id, amount):
            raise RuntimeError("DB write failed")
        orch.fiat.consume_reserved_for_mint = failing_consume
        key = str(uuid4())
        req = MintRequest(client_id="ALICE", amount=1000, idempotency_key=key)
        resp = orch.mint(req)
        assert resp.status == "failed"
        assert "dual compensation" in resp.message.lower()
        acct = orch.fiat.get("ALICE")
        assert acct.reserved == 0
        assert acct.available == 100_000


# Tests for the REDEEM operation — converting tokens back to cash.
class TestSagaRedeem:
    # Successful redeem: burn tokens on blockchain, credit fiat to account.
    def test_redeem_success(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = RedeemRequest(client_id="ALICE", amount=500, idempotency_key=key)
        resp = orch.redeem(req)
        assert resp.status == "success"
        acct = orch.fiat.get("ALICE")
        assert acct.available == 100_500

    # Calling redeem twice with the same key should return the same result.
    def test_redeem_idempotency(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = RedeemRequest(client_id="ALICE", amount=500, idempotency_key=key)
        resp1 = orch.redeem(req)
        assert resp1.status == "success"
        resp2 = orch.redeem(req)
        assert resp2.status == "success"
        assert "Idempotent" in resp2.message

    # If the blockchain burn fails, the redeem should fail without compensation needed.
    def test_redeem_onchain_failure(self, orch: SettlementOrchestrator):
        orch.chain.burn_tokens.side_effect = RuntimeError("Burn failed")
        key = str(uuid4())
        req = RedeemRequest(client_id="ALICE", amount=500, idempotency_key=key)
        resp = orch.redeem(req)
        assert resp.status == "failed"

    # If the fiat credit fails after the blockchain burn succeeded,
    # the tokens should be minted back (compensation).
    def test_redeem_fiat_credit_failure_compensates(self, orch: SettlementOrchestrator):
        def failing_credit(client_id, amount):
            raise RuntimeError("Ledger write failed")
        orch.fiat.credit_available = failing_credit
        key = str(uuid4())
        req = RedeemRequest(client_id="ALICE", amount=500, idempotency_key=key)
        resp = orch.redeem(req)
        assert resp.status == "failed"
        assert "compensating" in resp.message.lower()
        orch.chain.mint_tokens.assert_called_once_with("ALICE", 500)


# Tests for the TRANSFER operation — sending tokens between people.
class TestSagaTransfer:
    # Successfully transfer tokens from Alice to Bob.
    def test_transfer_success(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = TransferRequest(
            from_client_id="ALICE", to_client_id="BOB",
            amount=500, idempotency_key=key,
        )
        resp = orch.transfer(req)
        assert resp.status == "success"

    # Calling transfer twice with the same key should return the same result.
    def test_transfer_idempotency(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = TransferRequest(
            from_client_id="ALICE", to_client_id="BOB",
            amount=500, idempotency_key=key,
        )
        resp1 = orch.transfer(req)
        assert resp1.status == "success"
        resp2 = orch.transfer(req)
        assert resp2.status == "success"
        assert "Idempotent" in resp2.message

    # If the blockchain transfer fails, the transfer should report failure.
    def test_transfer_failure(self, orch: SettlementOrchestrator):
        orch.chain.transfer_tokens.side_effect = RuntimeError("Transfer failed")
        key = str(uuid4())
        req = TransferRequest(
            from_client_id="ALICE", to_client_id="BOB",
            amount=500, idempotency_key=key,
        )
        resp = orch.transfer(req)
        assert resp.status == "failed"


# Tests for the RESERVE operation — setting aside fiat money.
class TestSagaReserve:
    # Successfully reserve $50 from Alice's account.
    def test_reserve_success(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = ReserveRequest(client_id="ALICE", amount=5000, idempotency_key=key)
        resp = orch.reserve(req)
        assert resp.status == "success"
        acct = orch.fiat.get("ALICE")
        assert acct.reserved == 5000

    # Calling reserve twice with the same key should return the same result.
    def test_reserve_idempotency(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = ReserveRequest(client_id="ALICE", amount=5000, idempotency_key=key)
        resp1 = orch.reserve(req)
        assert resp1.status == "success"
        resp2 = orch.reserve(req)
        assert resp2.status == "success"
        assert "Idempotent" in resp2.message

    # Trying to reserve more than the available balance should fail.
    def test_reserve_insufficient(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = ReserveRequest(client_id="BOB", amount=999_999, idempotency_key=key)
        with pytest.raises(ValueError, match="Insufficient"):
            orch.reserve(req)
