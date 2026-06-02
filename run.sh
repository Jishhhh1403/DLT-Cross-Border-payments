#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
docker compose up --build -d
echo "Waiting for API..."
for i in $(seq 1 90); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "API ready: http://localhost:8000/docs"
    echo "Run demo: python scripts/run_settlement_demo.py"
    exit 0
  fi
  sleep 2
done
echo "API not ready. Check: docker compose logs settlement-api"
exit 1
