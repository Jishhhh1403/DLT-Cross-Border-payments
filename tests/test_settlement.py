"""Tests for Saga orchestration in SettlementOrchestrator with mocked blockchain client."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from backend.app.fiat_ledger import FiatLedger
from backend.app.models import MintRequest, RedeemRequest, ReserveRequest, TransferRequest
from backend.app.settlement import SettlementOrchestrator


def _make_mock_chain() -> MagicMock:
    chain = MagicMock()
    chain.client_addresses = {
        "ALICE": "0xALICE",
        "BOB": "0xBOB",
    }
    chain.token_balance.return_value = 0
    chain.total_supply.return_value = 0
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


@pytest.fixture
def orch():
    ledger = FiatLedger()
    chain = _make_mock_chain()
    return SettlementOrchestrator(ledger, chain)


class TestSagaMint:
    def test_mint_full_saga_success(self, orch: SettlementOrchestrator):
        orch.fiat.reserve("ALICE", 1000)
        key = str(uuid4())
        req = MintRequest(client_id="ALICE", amount=1000, idempotency_key=key)
        resp = orch.mint(req)
        assert resp.status == "success"
        acct = orch.fiat.get("ALICE")
        assert acct.reserved == 0
        assert acct.available == 99_000

    def test_mint_idempotency(self, orch: SettlementOrchestrator):
        orch.fiat.reserve("ALICE", 1000)
        key = str(uuid4())
        req = MintRequest(client_id="ALICE", amount=1000, idempotency_key=key)
        resp1 = orch.mint(req)
        assert resp1.status == "success"
        resp2 = orch.mint(req)
        assert resp2.status == "success"
        assert "Idempotent" in resp2.message

    def test_mint_insufficient_reserved(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = MintRequest(client_id="ALICE", amount=999_999, idempotency_key=key)
        with pytest.raises(ValueError, match="reserved"):
            orch.mint(req)

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


class TestSagaRedeem:
    def test_redeem_success(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = RedeemRequest(client_id="ALICE", amount=500, idempotency_key=key)
        resp = orch.redeem(req)
        assert resp.status == "success"
        acct = orch.fiat.get("ALICE")
        assert acct.available == 100_500

    def test_redeem_idempotency(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = RedeemRequest(client_id="ALICE", amount=500, idempotency_key=key)
        resp1 = orch.redeem(req)
        assert resp1.status == "success"
        resp2 = orch.redeem(req)
        assert resp2.status == "success"
        assert "Idempotent" in resp2.message

    def test_redeem_onchain_failure(self, orch: SettlementOrchestrator):
        orch.chain.burn_tokens.side_effect = RuntimeError("Burn failed")
        key = str(uuid4())
        req = RedeemRequest(client_id="ALICE", amount=500, idempotency_key=key)
        resp = orch.redeem(req)
        assert resp.status == "failed"

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


class TestSagaTransfer:
    def test_transfer_success(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = TransferRequest(
            from_client_id="ALICE", to_client_id="BOB",
            amount=500, idempotency_key=key,
        )
        resp = orch.transfer(req)
        assert resp.status == "success"

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

    def test_transfer_failure(self, orch: SettlementOrchestrator):
        orch.chain.transfer_tokens.side_effect = RuntimeError("Transfer failed")
        key = str(uuid4())
        req = TransferRequest(
            from_client_id="ALICE", to_client_id="BOB",
            amount=500, idempotency_key=key,
        )
        resp = orch.transfer(req)
        assert resp.status == "failed"


class TestSagaReserve:
    def test_reserve_success(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = ReserveRequest(client_id="ALICE", amount=5000, idempotency_key=key)
        resp = orch.reserve(req)
        assert resp.status == "success"
        acct = orch.fiat.get("ALICE")
        assert acct.reserved == 5000

    def test_reserve_idempotency(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = ReserveRequest(client_id="ALICE", amount=5000, idempotency_key=key)
        resp1 = orch.reserve(req)
        assert resp1.status == "success"
        resp2 = orch.reserve(req)
        assert resp2.status == "success"
        assert "Idempotent" in resp2.message

    def test_reserve_insufficient(self, orch: SettlementOrchestrator):
        key = str(uuid4())
        req = ReserveRequest(client_id="BOB", amount=999_999, idempotency_key=key)
        with pytest.raises(ValueError, match="Insufficient"):
            orch.reserve(req)
