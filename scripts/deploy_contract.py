"""
Deploy the DepositToken smart contract (if not already deployed) and grant permissions to the bank.

This script runs when the system starts up. It connects to the blockchain,
deploys (or loads) the deposit token contract, and makes sure the bank has
all the permissions it needs to create, destroy, and pause tokens.
"""

import sys

from backend.app.blockchain.client import BesuClient

# These are the blockchain IDs for the different permission roles.
# They're like passwords that identify each role on the blockchain.
MINTER_ROLE = "0x9f2df0fed2c77648de5860a4cc508cd0818c85b8b8a1ab4ceeef8d981c8956a6"
BURNER_ROLE = "0x3c11d16cbaffd01df69ce1c404f6340ee057498f5f00246190ea54220576a848"
PAUSER_ROLE = "0x65d7a28e3265b37a6474929f336521b332c1681b933f6cb9f3376673440d862a"


# The main deployment process.
def main() -> None:
    # Connect to the blockchain.
    client = BesuClient()
    if not client.connected:
        print("ERROR: Besu not connected", file=sys.stderr)
        sys.exit(1)
    # Either load an existing contract or deploy a new one.
    address = client.load_or_deploy_contract()
    bank_address = client.bank_address

    # Grant each required role to the bank if it doesn't already have it.
    roles = {
        "MINTER_ROLE": bytes.fromhex(MINTER_ROLE[2:]),
        "BURNER_ROLE": bytes.fromhex(BURNER_ROLE[2:]),
        "PAUSER_ROLE": bytes.fromhex(PAUSER_ROLE[2:]),
    }
    for role_name, role_bytes in roles.items():
        if not client.has_role(role_bytes, bank_address):
            receipt = client.grant_role(role_bytes, bank_address)
            print(f"Granted {role_name} to {bank_address} in tx={receipt['transactionHash'].hex()}")
        else:
            print(f"{role_name} already granted to {bank_address}")

    print(f"DepositToken at {address}")


if __name__ == "__main__":
    main()
