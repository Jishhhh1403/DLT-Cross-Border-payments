"""
Payment orchestration — coordinates off-chain fiat ledger with on-chain token operations.

This is the institutional "settlement engine" layer that Kinexys, Citi Token Services,
and Partior implement as middleware between core banking and the permissioned ledger.
"""

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
    TransferRequest,
)

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


class SettlementOrchestrator:
    def __init__(self, fiat: FiatLedger, chain: BesuClient) -> None:
        self.fiat = fiat
        self.chain = chain

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

    def _ledger_snapshot(self) -> LedgerSnapshot:
        return LedgerSnapshot(
            fiat_ledger=self.fiat.snapshot(),
            token_ledger=self._token_snapshot(),
        )

    def _response(
        self,
        operation: str,
        status: str,
        message: str,
        receipt=None,
    ) -> OperationResponse:
        evidence = BlockchainEvidence(**self.chain.receipt_to_evidence(receipt))
        return OperationResponse(
            operation=operation,
            status=status,
            message=message,
            ledger=self._ledger_snapshot(),
            blockchain=evidence,
            institutional_notes=INSTITUTIONAL_NOTES,
        )

    def reserve(self, req: ReserveRequest) -> OperationResponse:
        """
        Step 1 — Off-chain only.
        Locks fiat in reserved bucket before any on-chain mint (funds certainty).
        """
        self.fiat.reserve(req.client_id, req.amount)
        return self._response(
            operation="RESERVE",
            status="success",
            message=(
                f"Reserved {req.amount} cents fiat for {req.client_id.upper()}. "
                "No blockchain transaction — treasury ledger update only."
            ),
            receipt=None,
        )

    def mint(self, req: MintRequest) -> OperationResponse:
        """
        Step 2 — On-chain mint after fiat reservation consumed.
        Creates deposit tokens 1:1 with reserved fiat.
        """
        acct = self.fiat.get(req.client_id)
        if acct.reserved < req.amount:
            raise ValueError(
                f"Mint requires reserved fiat: {req.client_id} reserved={acct.reserved}, "
                f"requested={req.amount}. Call /reserve first."
            )
        self.fiat.consume_reserved_for_mint(req.client_id, req.amount)
        # Reserved consumed — fiat remains at bank, now represented as tokens
        receipt = self.chain.mint_tokens(req.client_id, req.amount)
        return self._response(
            operation="MINT",
            status="success",
            message=(
                f"Minted {req.amount} deposit tokens to {req.client_id.upper()} on-ledger. "
                f"totalSupply on-chain = {self.chain.total_supply()}"
            ),
            receipt=receipt,
        )

    def transfer(self, req: TransferRequest) -> OperationResponse:
        """
        Step 3 — On-chain peer transfer.
        Fiat at bank unchanged; only token ownership moves (claim transfer).
        """
        receipt = self.chain.transfer_tokens(
            req.from_client_id, req.to_client_id, req.amount
        )
        return self._response(
            operation="TRANSFER",
            status="success",
            message=(
                f"Transferred {req.amount} tokens from {req.from_client_id.upper()} "
                f"to {req.to_client_id.upper()} on-ledger."
            ),
            receipt=receipt,
        )

    def redeem(self, req: RedeemRequest) -> OperationResponse:
        """
        Step 4 — Burn tokens, credit fiat available balance.
        Completes detokenization lifecycle.
        """
        receipt = self.chain.burn_tokens(req.client_id, req.amount)
        self.fiat.credit_available(req.client_id, req.amount)
        return self._response(
            operation="REDEEM",
            status="success",
            message=(
                f"Burned {req.amount} tokens and credited {req.amount} cents fiat "
                f"to {req.client_id.upper()} available balance."
            ),
            receipt=receipt,
        )

    def balances(self) -> OperationResponse:
        return self._response(
            operation="BALANCES",
            status="success",
            message="Current fiat and token ledger snapshot.",
            receipt=None,
        )
