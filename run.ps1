# Start tokenized deposit POC (requires Docker Desktop)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker not found. Install Docker Desktop: https://docs.docker.com/desktop/install/windows-install/"
}

docker compose up --build -d
Write-Host "Waiting for API..."
$ok = $false
for ($i = 0; $i -lt 120; $i++) {
    try {
        $r = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 2
        if ($r.status -eq "ok") { $ok = $true; break }
    } catch {}
    Start-Sleep -Seconds 2
}

if (-not $ok) {
    Write-Host "API not ready. Current service status:"
    docker compose ps -a
    Write-Host "\nLast Besu logs:"
    docker compose logs --tail=120 besu
    Write-Host "\nLast API logs:"
    docker compose logs --tail=120 settlement-api
    exit 1
}

Write-Host "API ready: http://localhost:8000/docs"
Write-Host "Run demo: python scripts/run_settlement_demo.py"