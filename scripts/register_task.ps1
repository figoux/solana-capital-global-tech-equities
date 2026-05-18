# Register the daily ETL with Windows Task Scheduler.
#
# Run this once as Administrator (right-click PowerShell -> Run as Administrator):
#   .\scripts\register_task.ps1
#
# It schedules daily_update.ps1 to run every day at 07:00 in S4U mode
# (no password prompt needed, runs even if the user is not logged in).

param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$TaskName    = "SolanaTech_DailyETL",
    [string]$AtTime      = "7:00am"
)

$scriptPath = Join-Path $ProjectRoot "scripts\daily_update.ps1"

if (-not (Test-Path $scriptPath)) {
    Write-Error "Could not find $scriptPath. Pass -ProjectRoot <path> if the repo lives elsewhere."
    exit 1
}

$action    = New-ScheduledTaskAction -Execute "powershell.exe" `
                -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
$trigger   = New-ScheduledTaskTrigger -Daily -At $AtTime
$settings  = New-ScheduledTaskSettingsSet `
                -StartWhenAvailable -AllowStartIfOnBatteries `
                -DontStopIfGoingOnBatteries -RunOnlyIfNetworkAvailable `
                -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType S4U -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Daily ETL + auto-deploy to Render" `
    -Force

Write-Host ""
Write-Host "=== Task registered successfully ===" -ForegroundColor Green
Write-Host "Task name: $TaskName" -ForegroundColor Green
Write-Host "Will run daily at $AtTime against $scriptPath" -ForegroundColor Green
Write-Host ""
