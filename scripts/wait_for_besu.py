"""Wait until Besu JSON-RPC is accepting connections before deploy."""

import os
import sys
import time

from web3 import Web3

RPC = os.getenv("BESU_RPC_URL", "http://besu:8545")
MAX_WAIT = 180

w3 = Web3(Web3.HTTPProvider(RPC))
for i in range(MAX_WAIT):
    try:
        if w3.is_connected():
            block = w3.eth.block_number
            print(f"Besu ready at {RPC}, block={block}")
            sys.exit(0)
    except Exception:
        pass
    time.sleep(1)

print(f"Timeout waiting for Besu at {RPC}", file=sys.stderr)
sys.exit(1)
