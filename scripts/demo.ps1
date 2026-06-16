# ---------------------------------------------------------------------------
# GRC Assistant - local demo launcher (Windows / PowerShell)
#
#   powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
#   $env:PORT=8080; powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
#
# Starts the aiohttp server (web UI + /chat + Teams endpoint), waits until it is
# healthy, opens the browser, and prints the demo questions. Enter stops it.
# ---------------------------------------------------------------------------
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$Port = if ($env:PORT) { $env:PORT } else { "3978" }
$Url  = "http://localhost:$Port"

$Py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Py) { $Py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $Py) { Write-Host "Python 3.10+ not found. Install Python and retry." -ForegroundColor Red; exit 1 }

if (-not (Test-Path ".env")) { Write-Host ".env not found - copy .env.example to .env and fill in your keys." -ForegroundColor Yellow }
if (-not (Test-Path "vector_db\index.faiss")) { Write-Host "vector_db\index.faiss missing - build it first:  python ingest.py" -ForegroundColor Yellow }

Write-Host "Starting GRC Assistant on $Url (loading the index can take ~30s)..."
$server = Start-Process -FilePath $Py -ArgumentList "teams_bot.py" -PassThru -NoNewWindow

try {
    $ready = $false
    for ($i = 0; $i -lt 120; $i++) {
        try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "$Url/health" | Out-Null; $ready = $true; break }
        catch { Start-Sleep -Seconds 2 }
    }
    if ($ready) { Write-Host "Ready." -ForegroundColor Green } else { Write-Host "Server not healthy yet - check the logs above." -ForegroundColor Yellow }

    Start-Process $Url

    Write-Host ""
    Write-Host "Cau hoi demo (dan vao o chat):"
    Write-Host "  1. tham khao tai lieu gi ve cap quyen truy cap      -> goi y tai lieu"
    Write-Host "  2. quy trinh xu ly su co bao mat gom nhung buoc nao  -> RAG + trich dan [n]"
    Write-Host "  3. QT-01 co bao nhieu version                        -> liet ke phien ban"
    Write-Host "  4. ai la tac gia cua ZION-TC-13                      -> metadata"
    Write-Host "  5. co bao nhieu tai lieu                             -> catalog (52)"
    Write-Host "  6. ban lam duoc gi                                   -> tra loi than thien"
    Write-Host ""
    Read-Host "Press Enter to stop"
}
finally {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force }
    Write-Host "Stopped GRC Assistant."
}
