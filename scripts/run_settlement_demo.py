#!/usr/bin/env python3
"""
End-to-end settlement demo: Alice sends $100 to Bob.

This script walks through the entire settlement lifecycle:
1. Alice reserves $100 from her bank account
2. Alice mints $100 in deposit tokens
3. Alice transfers the tokens to Bob
4. Bob redeems the tokens back to real money

Run this after starting the system with: docker compose up
  python scripts/run_settlement_demo.py
"""

import json
import sys
import time

import httpx

BASE = "http://localhost:8000"   # The API server address
AMOUNT = 10_000                  # $100.00 (amounts are in cents)


# Send a POST request to the API (used for creating things).
def post(path: str, body: dict) -> dict:
    r = httpx.post(f"{BASE}{path}", json=body, timeout=60.0)
    r.raise_for_status()
    return r.json()


# Send a GET request to the API (used for reading data).
def get(path: str) -> dict:
    r = httpx.get(f"{BASE}{path}", timeout=30.0)
    r.raise_for_status()
    return r.json()


# Print a nicely formatted step header and data.
def print_step(title: str, data: dict) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    print(json.dumps(data, indent=2, default=str))


# Run the complete demo.
def main() -> None:
    # Wait for the API to be ready (check up to 60 seconds).
    for _ in range(30):
        try:
            health = get("/health")
            if health.get("status") == "ok":
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        print("API not ready", file=sys.stderr)
        sys.exit(1)

    # Show initial balances before we start.
    print_step("INITIAL STATE", get("/balances"))

    # Step 1: Alice sets aside $100 from her bank account.
    print_step("STEP 1 - RESERVE $100 fiat (Alice)", post("/reserve", {"client_id": "ALICE", "amount": AMOUNT}))

    # Step 2: Convert that reserved money into digital deposit tokens.
    print_step("STEP 2 - MINT $100 deposit tokens (Alice)", post("/mint", {"client_id": "ALICE", "amount": AMOUNT}))

    # Step 3: Send the tokens from Alice to Bob on the blockchain.
    print_step(
        "STEP 3 - TRANSFER tokens Alice -> Bob",
        post(
            "/transfer",
            {"from_client_id": "ALICE", "to_client_id": "BOB", "amount": AMOUNT},
        ),
    )

    # Step 4: Bob converts the tokens back into real money in his bank account.
    print_step("STEP 4 - REDEEM tokens -> fiat (Bob)", post("/redeem", {"client_id": "BOB", "amount": AMOUNT}))

    # Show the final balances after everything is done.
    print_step("FINAL STATE", get("/balances"))
    print("\nSettlement lifecycle complete.")


if __name__ == "__main__":
    main()
