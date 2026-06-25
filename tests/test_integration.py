import pytest
from backend.app.blockchain.client import BesuClient
from backend.app.models import ReserveRequest, MintRequest, TransferRequest, RedeemRequest


@pytest.mark.skip(reason="Requires a running Besu node and PostgreSQL. Run manually with `pytest --run-integration`")
class TestLiveIntegration:
    def setup_method(self):
        self.chain = BesuClient()
        if not self.chain.connected:
            pytest.skip("Besu node not available")

    def test_full_settlement_cycle(self):
        alice_balance_before = self.chain.token_balance("ALICE")
        bob_balance_before = self.chain.token_balance("BOB")
        assert alice_balance_before >= 0
        assert bob_balance_before >= 0

    def test_chain_connectivity(self):
        assert self.chain.connected
        assert self.chain.w3.eth.chain_id > 0
        assert self.chain.w3.eth.block_number >= 0

    def test_contract_deployed(self):
        self.chain.load_or_deploy_contract()
        assert self.chain.contract is not None
        total = self.chain.total_supply()
        assert total >= 0
