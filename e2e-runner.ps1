#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$BackendDir = "D:\date-wise\06-04-2026(live current autopilot)\impulse_analyst_v2\backend"
$FrontendDir = "D:\date-wise\06-04-2026(live current autopilot)\impulse_analyst_v2\frontend"
$LogDir = Join-Path $BackendDir "e2e-logs"

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

Write-Host "=== Starting Backend Server ==="
$backendJob = Start-Job -ScriptBlock {
    param($dir, $log)
    Set-Location $dir
    $env:APP_ENV = "test"
    & ".\venv\Scripts\python.exe" run.py *>&1 | Out-File -Encoding utf8 -FilePath $log
} -ArgumentList $BackendDir, (Join-Path $LogDir "backend.log")

Start-Sleep -Seconds 10

Write-Host "=== Starting Frontend Dev Server ==="
$frontendJob = Start-Job -ScriptBlock {
    param($dir, $log)
    Set-Location $dir
    npm run dev *>&1 | Out-File -Encoding utf8 -FilePath $log
} -ArgumentList $FrontendDir, (Join-Path $LogDir "frontend.log")

Start-Sleep -Seconds 15

Write-Host "=== Checking Servers ==="
$backendOk = $false
$frontendOk = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8002/api/auth/me" -Method Get -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $backendOk = $true }
    } catch {}
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $frontendOk = $true }
    } catch {}
    if ($backendOk -and $frontendOk) { break }
    Start-Sleep -Seconds 3
}

if (-not $backendOk) { Write-Host "Backend failed to start"; Stop-Job $backendJob, $frontendJob; Remove-Job $backendJob, $frontendJob -Force; exit 1 }
if (-not $frontendOk) { Write-Host "Frontend failed to start"; Stop-Job $backendJob, $frontendJob; Remove-Job $backendJob, $frontendJob -Force; exit 1 }
Write-Host "Both servers are running!"

Write-Host "=== Running E2E Tests ==="
Set-Location $FrontendDir
npx playwright test --reporter=list 2>&1
$exitCode = $LASTEXITCODE

Write-Host "=== Cleaning Up ==="
Stop-Job $backendJob -ErrorAction SilentlyContinue
Stop-Job $frontendJob -ErrorAction SilentlyContinue
Remove-Job $backendJob -Force -ErrorAction SilentlyContinue
Remove-Job $frontendJob -Force -ErrorAction SilentlyContinue

Write-Host "=== Done (exit code: $exitCode) ==="
exit $exitCode
