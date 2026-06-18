"""
Wait until the Besu blockchain node is ready to accept connections.

This script is used during startup. It keeps checking if the Besu blockchain
node is online, and only exits successfully once the node is reachable.
This prevents other services from starting before the blockchain is ready.
"""

import os
import sys
import time

from web3 import Web3

RPC = os.getenv("BESU_RPC_URL", "http://besu:8545")   # Where to find the Besu node
MAX_WAIT = 180                                          # Maximum wait time in seconds (3 minutes)

w3 = Web3(Web3.HTTPProvider(RPC))
# Keep trying to connect, checking once per second.
for i in range(MAX_WAIT):
    try:
        if w3.is_connected():
            block = w3.eth.block_number
            print(f"Besu ready at {RPC}, block={block}")
            sys.exit(0)
    except Exception:
        pass
    time.sleep(1)

# If we get here, the node never came online within the time limit.
print(f"Timeout waiting for Besu at {RPC}", file=sys.stderr)
sys.exit(1)
