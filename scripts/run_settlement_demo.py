#!/usr/bin/env python3
"""
End-to-end settlement demo: Alice sends $100 to Bob.

Run after: docker compose up
  python scripts/run_settlement_demo.py
"""

import json
import sys
import time

import httpx

BASE = "http://localhost:8000"
AMOUNT = 10_000  # $100.00 in cents


def post(path: str, body: dict) -> dict:
    r = httpx.post(f"{BASE}{path}", json=body, timeout=60.0)
    r.raise_for_status()
    return r.json()


def get(path: str) -> dict:
    r = httpx.get(f"{BASE}{path}", timeout=30.0)
    r.raise_for_status()
    return r.json()


def print_step(title: str, data: dict) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    print(json.dumps(data, indent=2, default=str))


def main() -> None:
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

    print_step("INITIAL STATE", get("/balances"))

    print_step("STEP 1 - RESERVE $100 fiat (Alice)", post("/reserve", {"client_id": "ALICE", "amount": AMOUNT}))

    print_step("STEP 2 - MINT $100 deposit tokens (Alice)", post("/mint", {"client_id": "ALICE", "amount": AMOUNT}))

    print_step(
        "STEP 3 - TRANSFER tokens Alice -> Bob",
        post(
            "/transfer",
            {"from_client_id": "ALICE", "to_client_id": "BOB", "amount": AMOUNT},
        ),
    )

    print_step("STEP 4 - REDEEM tokens -> fiat (Bob)", post("/redeem", {"client_id": "BOB", "amount": AMOUNT}))

    print_step("FINAL STATE", get("/balances"))
    print("\nSettlement lifecycle complete.")


if __name__ == "__main__":
    main()
