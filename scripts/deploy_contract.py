"""Deploy DepositToken if not already deployed (container startup)."""

import sys

from backend.app.blockchain.client import BesuClient


def main() -> None:
    client = BesuClient()
    if not client.connected:
        print("ERROR: Besu not connected", file=sys.stderr)
        sys.exit(1)
    address = client.load_or_deploy_contract()
    print(f"DepositToken at {address}")


if __name__ == "__main__":
    main()
