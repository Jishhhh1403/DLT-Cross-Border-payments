# Run

## Prerequisites

- Docker Desktop (running)
- Python 3.12+ (for demo script only)

## Start stack

**Windows (PowerShell):**

```powershell
cd tokenized-deposit-poc
.\run.ps1
```

**macOS / Linux:**

```bash
cd tokenized-deposit-poc
chmod +x run.sh
./run.sh
```

**Or manually:**

```bash
docker compose up --build -d
```

Wait ~60–120s (first build installs solc). API: http://localhost:8000/docs

## End-to-end demo

```bash
pip install httpx
python scripts/run_settlement_demo.py
```

## Stop

```bash
docker compose down
```

## Reset chain + contract

```bash
docker compose down -v
docker compose up --build -d
```

## Logs

```bash
docker compose logs -f besu
docker compose logs -f settlement-api
```

## Manual API (curl)

See [docs/API_EXAMPLES.md](docs/API_EXAMPLES.md)
