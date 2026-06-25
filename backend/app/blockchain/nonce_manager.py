from threading import Lock
from web3 import Web3


class NonceManager:
    def __init__(self, w3: Web3):
        self.w3 = w3
        self._lock = Lock()
        self._local_nonces: dict[str, int] = {}

    def get_nonce(self, address: str) -> int:
        address = address.lower()
        with self._lock:
            onchain = self.w3.eth.get_transaction_count(address)
            local = self._local_nonces.get(address, -1)
            nonce = max(onchain, local + 1)
            self._local_nonces[address] = nonce
            return nonce

    def reset(self, address: str):
        address = address.lower()
        with self._lock:
            self._local_nonces.pop(address, None)

    def reset_all(self):
        with self._lock:
            self._local_nonces.clear()
