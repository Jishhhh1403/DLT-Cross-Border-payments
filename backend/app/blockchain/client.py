"""
web3.py integration with Hyperledger Besu.

Encapsulates contract deployment, mint, transfer, burn, and receipt parsing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from eth_account import Account
from web3 import Web3
from web3.contract import Contract
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxReceipt

from backend.app.config import settings

DEPOSIT_TOKEN_ABI: list[dict[str, Any]] = [
    {
        "inputs": [{"internalType": "address", "name": "initialBankOperator", "type": "address"}],
        "stateMutability": "nonpayable",
        "type": "constructor",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "from", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "to", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "to", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "operator", "type": "address"},
        ],
        "name": "Mint",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "from", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "operator", "type": "address"},
        ],
        "name": "Burn",
        "type": "event",
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "burn",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class BesuClient:
    def __init__(self) -> None:
        self.w3 = Web3(Web3.HTTPProvider(settings.besu_rpc_url))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.bank_account = Account.from_key(settings.bank_private_key)
        self.client_addresses = {
            "ALICE": Web3.to_checksum_address(settings.alice_onchain_address),
            "BOB": Web3.to_checksum_address(settings.bob_onchain_address),
        }
        self._contract: Contract | None = None

    def _fee_fields(self) -> dict[str, int]:
        # Use EIP-1559 fee fields so txs remain valid when baseFee > 0.
        base = int(self.w3.eth.gas_price)
        priority = max(1, base // 10)
        return {
            "maxPriorityFeePerGas": priority,
            "maxFeePerGas": base + priority,
        }

    @property
    def connected(self) -> bool:
        return self.w3.is_connected()

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
                # If address is invalid or chain has been reset, redeploy below.
                pass
        return self.deploy_contract()

    def _bind_contract(self, address: str) -> None:
        checksum = Web3.to_checksum_address(address)
        self._contract = self.w3.eth.contract(address=checksum, abi=DEPOSIT_TOKEN_ABI)

    @property
    def contract(self) -> Contract:
        if self._contract is None:
            raise RuntimeError("Contract not loaded — deploy first")
        return self._contract

    def compile_contract(self) -> tuple[list[dict[str, Any]], str]:
        artifact_paths = (
            Path(settings.contracts_dir) / "build" / "DepositToken.json",
            Path("/app/contracts/build/DepositToken.json"),
        )
        for path in artifact_paths:
            if path.exists():
                import json

                data = json.loads(path.read_text(encoding="utf-8"))
                return data["abi"], data["bin"]
        raise RuntimeError(
            "Missing contract artifact contracts/build/DepositToken.json. "
            "Run: python scripts/compile_contract.py"
        )

    def deploy_contract(self) -> str:
        abi, bytecode = self.compile_contract()
        ContractFactory = self.w3.eth.contract(abi=abi, bytecode=bytecode)
        bank_address = self.bank_account.address

        tx = ContractFactory.constructor(bank_address).build_transaction(
            {
                "from": bank_address,
                "nonce": self.w3.eth.get_transaction_count(bank_address),
                "gas": 12_000_000,
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

        global DEPOSIT_TOKEN_ABI
        DEPOSIT_TOKEN_ABI = abi
        self._bind_contract(address)
        return address

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

    def mint_tokens(self, client_id: str, amount: int) -> TxReceipt:
        to_addr = self.client_addresses[client_id.upper()]
        return self._send_bank_tx(self.contract.functions.mint(to_addr, amount))

    def burn_tokens(self, client_id: str, amount: int) -> TxReceipt:
        from_addr = self.client_addresses[client_id.upper()]
        return self._send_bank_tx(self.contract.functions.burn(from_addr, amount))

    def transfer_tokens(self, from_client: str, to_client: str, amount: int) -> TxReceipt:
        # POC: Alice signs her own transfer (institutional HSM would sign in production)
        from_key = os.getenv(
            f"{from_client.upper()}_PRIVATE_KEY",
            "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78627d",  # Alice dev key
        )
        to_addr = self.client_addresses[to_client.upper()]
        return self._send_client_tx(
            from_key,
            self.contract.functions.transfer(to_addr, amount),
        )

    def token_balance(self, client_id: str) -> int:
        addr = self.client_addresses[client_id.upper()]
        return int(self.contract.functions.balanceOf(addr).call())

    def total_supply(self) -> int:
        return int(self.contract.functions.totalSupply().call())

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
