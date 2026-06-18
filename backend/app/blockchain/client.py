"""
web3.py integration with Hyperledger Besu.

This file handles all communication with the blockchain. It's like a translator
between our application and the Hyperledger Besu blockchain network.
It can deploy contracts, create tokens, transfer them, destroy them, and read balances.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eth_account import Account
from web3 import Web3
from web3.contract import Contract
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxReceipt

from backend.app.config import settings


# Load the compiled smart contract's ABI (interface description) and bytecode (compiled code).
# The ABI is like a manual that tells us what functions the contract has.
def _load_artifact() -> tuple[list[dict[str, Any]], str]:
    artifact_paths = (
        Path(settings.contracts_dir) / "build" / "DepositToken.json",
        Path("/app/contracts/build/DepositToken.json"),
    )
    for path in artifact_paths:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data["abi"], data["bin"]
    raise RuntimeError(
        "Missing contract artifact contracts/build/DepositToken.json. "
        "Run: python scripts/compile_contract.py"
    )


# This is our connection to the blockchain. It knows how to:
# - Connect to Hyperledger Besu (the blockchain network)
# - Deploy the deposit token smart contract
# - Create, transfer, and destroy tokens
# - Check balances and read blockchain data
class BesuClient:
    def __init__(self) -> None:
        # Set up the connection to the blockchain node.
        self.w3 = Web3(Web3.HTTPProvider(settings.besu_rpc_url))
        # Besu needs this middleware to handle its Proof of Authority consensus.
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        # The bank's blockchain account (identified by its private key).
        self.bank_account = Account.from_key(settings.bank_private_key)
        # Map client names to their blockchain addresses.
        self.client_addresses = {
            "ALICE": Web3.to_checksum_address(settings.alice_onchain_address),
            "BOB": Web3.to_checksum_address(settings.bob_onchain_address),
        }
        self._contract: Contract | None = None
        self._abi, self._bytecode = _load_artifact()

    # Calculate the fee for processing a transaction on the blockchain.
    # Like calculating how much to pay for the electricity used by the blockchain computers.
    def _fee_fields(self) -> dict[str, int]:
        base = int(self.w3.eth.gas_price)
        priority = max(1, base // 10)
        return {
            "maxPriorityFeePerGas": priority,
            "maxFeePerGas": base + priority,
        }

    # Check if we are connected to the blockchain.
    @property
    def connected(self) -> bool:
        return self.w3.is_connected()

    # Try to load an already-deployed contract, or deploy a new one if needed.
    def load_or_deploy_contract(self) -> str:
        path = Path(settings.contract_address_file)
        if path.exists():
            address = path.read_text().strip()
            try:
                checksum = Web3.to_checksum_address(address)
                code = self.w3.eth.get_code(checksum)
                if code and code != b"":
                    self._bind_contract(address)
                    return address
            except Exception:
                pass
        return self.deploy_contract()

    # Tell our client which contract address to use (bind to it).
    def _bind_contract(self, address: str) -> None:
        checksum = Web3.to_checksum_address(address)
        self._contract = self.w3.eth.contract(address=checksum, abi=self._abi)

    # Get the contract we're working with. Error if we haven't loaded one yet.
    @property
    def contract(self) -> Contract:
        if self._contract is None:
            raise RuntimeError("Contract not loaded — deploy first")
        return self._contract

    # Deploy a new deposit token contract to the blockchain.
    # This is like building and opening a new bank vault on the blockchain.
    def deploy_contract(self) -> str:
        ContractFactory = self.w3.eth.contract(abi=self._abi, bytecode=self._bytecode)
        bank_address = self.bank_account.address

        tx = ContractFactory.constructor(bank_address).build_transaction(
            {
                "from": bank_address,
                "nonce": self.w3.eth.get_transaction_count(bank_address),
                "gas": 15_000_000,
                "chainId": settings.chain_id,
                **self._fee_fields(),
            }
        )
        signed = self.bank_account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt["status"] != 1:
            raise RuntimeError(
                f"Contract deployment failed: tx={tx_hash.hex()} gasUsed={receipt['gasUsed']}"
            )
        address = receipt["contractAddress"]

        out = Path(settings.contract_address_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(address)

        self._bind_contract(address)
        return address

    # Send a transaction signed by the bank's account.
    # Used for bank-only operations like minting and burning tokens.
    def _send_bank_tx(self, fn) -> TxReceipt:
        bank_address = self.bank_account.address
        tx = fn.build_transaction(
            {
                "from": bank_address,
                "nonce": self.w3.eth.get_transaction_count(bank_address),
                "gas": 500_000,
                "chainId": settings.chain_id,
                **self._fee_fields(),
            }
        )
        signed = self.bank_account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt["status"] != 1:
            raise RuntimeError(
                f"Bank tx failed: tx={tx_hash.hex()} gasUsed={receipt['gasUsed']}"
            )
        return receipt

    # Send a transaction signed by a client (non-bank) account.
    # Used for client operations like transferring tokens.
    def _send_client_tx(self, private_key: str, fn) -> TxReceipt:
        account = Account.from_key(private_key)
        tx = fn.build_transaction(
            {
                "from": account.address,
                "nonce": self.w3.eth.get_transaction_count(account.address),
                "gas": 300_000,
                "chainId": settings.chain_id,
                **self._fee_fields(),
            }
        )
        signed = account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt["status"] != 1:
            raise RuntimeError(
                f"Client tx failed: tx={tx_hash.hex()} gasUsed={receipt['gasUsed']}"
            )
        return receipt

    # Create new tokens and give them to a client. Only the bank can do this.
    def mint_tokens(self, client_id: str, amount: int) -> TxReceipt:
        to_addr = self.client_addresses[client_id.upper()]
        return self._send_bank_tx(self.contract.functions.mint(to_addr, amount))

    # Destroy tokens belonging to a client. Only the bank can do this.
    def burn_tokens(self, client_id: str, amount: int) -> TxReceipt:
        from_addr = self.client_addresses[client_id.upper()]
        return self._send_bank_tx(self.contract.functions.burn(from_addr, amount))

    # Transfer tokens from one client to another on the blockchain.
    def transfer_tokens(self, from_client: str, to_client: str, amount: int) -> TxReceipt:
        from_key = settings.alice_private_key
        to_addr = self.client_addresses[to_client.upper()]
        return self._send_client_tx(
            from_key,
            self.contract.functions.transfer(to_addr, amount),
        )

    # Check how many tokens a client has on the blockchain.
    def token_balance(self, client_id: str) -> int:
        addr = self.client_addresses[client_id.upper()]
        return int(self.contract.functions.balanceOf(addr).call())

    # Check the total number of deposit tokens in existence.
    def total_supply(self) -> int:
        return int(self.contract.functions.totalSupply().call())

    # Give a specific role (permission) to an account on the smart contract.
    def grant_role(self, role_bytes32: bytes, account: str) -> TxReceipt:
        checksum = Web3.to_checksum_address(account)
        return self._send_bank_tx(
            self.contract.functions.grantRole(role_bytes32, checksum)
        )

    # Remove a specific role (permission) from an account.
    def revoke_role(self, role_bytes32: bytes, account: str) -> TxReceipt:
        checksum = Web3.to_checksum_address(account)
        return self._send_bank_tx(
            self.contract.functions.revokeRole(role_bytes32, checksum)
        )

    # Check if an account has a specific role.
    def has_role(self, role_bytes32: bytes, account: str) -> bool:
        checksum = Web3.to_checksum_address(account)
        return bool(self.contract.functions.hasRole(role_bytes32, checksum).call())

    # Pause the contract (emergency stop all operations).
    def pause_contract(self) -> TxReceipt:
        return self._send_bank_tx(self.contract.functions.pause())

    # Unpause the contract (resume normal operations).
    def unpause_contract(self) -> TxReceipt:
        return self._send_bank_tx(self.contract.functions.unpause())

    # Read the event logs from a blockchain transaction receipt.
    # Event logs are like the blockchain's record of what happened during a transaction.
    def parse_receipt_logs(self, receipt: TxReceipt) -> list[dict[str, Any]]:
        logs: list[dict[str, Any]] = []
        for log in receipt["logs"]:
            try:
                decoded = self.contract.events.Transfer().process_log(log)
                logs.append({"event": "Transfer", "args": dict(decoded["args"])})
            except Exception:
                pass
            try:
                decoded = self.contract.events.Mint().process_log(log)
                logs.append({"event": "Mint", "args": dict(decoded["args"])})
            except Exception:
                pass
            try:
                decoded = self.contract.events.Burn().process_log(log)
                logs.append({"event": "Burn", "args": dict(decoded["args"])})
            except Exception:
                pass
        return logs

    # Convert a blockchain receipt into a simpler evidence format for our API responses.
    # If there's no receipt (off-chain operation), return empty evidence.
    def receipt_to_evidence(self, receipt: TxReceipt | None) -> dict[str, Any]:
        if receipt is None:
            return {
                "transaction_hash": None,
                "block_number": None,
                "gas_used": None,
                "event_logs": [],
            }
        return {
            "transaction_hash": receipt["transactionHash"].hex(),
            "block_number": receipt["blockNumber"],
            "gas_used": receipt["gasUsed"],
            "event_logs": self.parse_receipt_logs(receipt),
        }
