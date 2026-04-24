# ============================================================
# daily_update.ps1 - ETL diario + deploy automatico pro Render
# ============================================================
# Rodado pelo Task Scheduler.
# Fluxo:
#   1. cd no projeto
#   2. roda ETL modules (prices, fundamentals, vol, earnings, pairs)
#   3. se dashboard.db mudou -> git add/commit/push -> Render redeploy
#   4. se nada mudou, sai silencioso
#   5. log tudo em logs/daily_update_YYYY-MM-DD.log
# ============================================================

$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"       # evita UnicodeEncodeError em prints ETL
$env:PYTHONUTF8 = "1"
$projectRoot = "C:\Users\filip\OneDrive\Documentos\Claude\Projects\Solana Global Tech"
Set-Location $projectRoot

# Logs
$logDir = Join-Path $projectRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$today = Get-Date -Format "yyyy-MM-dd"
$logFile = Join-Path $logDir "daily_update_$today.log"

function Log {
    param([string]$msg)
    $ts = Get-Date -Format "HH:mm:ss"
    "[$ts] $msg" | Tee-Object -FilePath $logFile -Append
}

Log "=== Daily update started ==="
Log "Project: $projectRoot"

# Python no PATH do usuario
$py = "python"

# ETL pipeline - ordem importa (pairs depende de prices)
$etlSteps = @(
    @{ name = "prices_yf";          cmd = "backend.etl.prices_yf" },
    @{ name = "fundamentals_yf";    cmd = "backend.etl.fundamentals_yf" },
    @{ name = "vol_yf";             cmd = "backend.etl.vol_yf" },
    @{ name = "earnings_cal";       cmd = "backend.etl.earnings_cal" },
    @{ name = "earnings_history";   cmd = "backend.etl.earnings_history_yf" },
    @{ name = "pairs_compute";      cmd = "backend.etl.pairs_compute" }
)

$failed = @()
foreach ($step in $etlSteps) {
    Log ("-> ETL: " + $step.name)
    & $py -m $step.cmd *>&1 | Tee-Object -FilePath $logFile -Append
    if ($LASTEXITCODE -ne 0) {
        Log ("   FAILED (exit " + $LASTEXITCODE + ")")
        $failed += $step.name
    } else {
        Log "   ok"
    }
}

if ($failed.Count -gt 0) {
    Log ("ETL failures: " + ($failed -join ", ") + " - ABORTING deploy")
    Log "=== Daily update FINISHED WITH ERRORS ==="
    exit 1
}

# Verifica se dashboard.db mudou
Log "-> git status check"
$dbChanged = git status --porcelain backend/db/dashboard.db
if (-not $dbChanged) {
    Log "   dashboard.db unchanged - nothing to deploy"
    Log "=== Daily update DONE (no changes) ==="
    exit 0
}

# Commit + push
Log "-> Committing dashboard.db"
git add backend/db/dashboard.db
git commit -m "Daily ETL refresh $today" *>&1 | Tee-Object -FilePath $logFile -Append
if ($LASTEXITCODE -ne 0) {
    Log "   git commit failed"
    exit 1
}

Log "-> Pushing to origin/main"
git push origin main *>&1 | Tee-Object -FilePath $logFile -Append
if ($LASTEXITCODE -ne 0) {
    Log "   git push failed - CHECK CREDS"
    exit 1
}

Log "   pushed - Render will redeploy in ~2min"
Log "=== Daily update DONE ==="
exit 0
