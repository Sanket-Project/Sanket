param([ValidateSet('all','api','ml','worker','frontend')][string]$Mode='all')
$ErrorActionPreference='Stop'
$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
if ($Mode -eq 'all') {
    docker start sanket-fashion-audit-db sanket-fashion-audit-redis
    $shellPath=(Get-Process -Id $PID).Path
    foreach ($service in @('api','ml','worker','frontend')) {
        $port=@{api=8010;ml=8001;frontend=5173}[$service]
        if ($port -and (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)) { continue }
        if ($service -eq 'worker' -and (Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'python.exe' -and $_.CommandLine -like '*Prisma*arq app.workers.forecast_worker.WorkerSettings*'})) { continue }
        Start-Process -FilePath $shellPath -WindowStyle Hidden -ArgumentList @('-NoProfile','-File',('"'+$PSCommandPath+'"'),'-Mode',$service)
    }
    Write-Output 'Audit demo: http://127.0.0.1:5173/login . Allow up to 90 seconds for model startup.'
    return
}
$env:DATABASE_URL='postgresql+asyncpg://sanket_app:changeme@localhost:55432/sanket'
$env:REDIS_URL='redis://localhost:56379/0'
$env:ML_API_URL='http://127.0.0.1:8001'
$env:ML_SERVICE_TOKEN='sanket-fashion-audit-local'
$env:FIREBASE_PROJECT_ID=''
$env:FIREBASE_CREDENTIALS_PATH=''
$env:FIREBASE_WEB_API_KEY=''
$env:SHOPIFY_POLL_ENABLED='false'
switch ($Mode) {
    'api' { Set-Location (Join-Path $repoRoot 'backend'); & .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010 *> (Join-Path $PSScriptRoot 'demo-api.log') }
    'worker' { Set-Location (Join-Path $repoRoot 'backend'); & .venv/Scripts/python.exe -m arq app.workers.forecast_worker.WorkerSettings *> (Join-Path $PSScriptRoot 'demo-worker.log') }
    'ml' {
        Set-Location (Join-Path $repoRoot 'backend/ml')
        $env:ML_DATABASE_URL='postgresql://sanket_app:changeme@localhost:55432/sanket'
        $env:ML_DATABASE_ASYNC_URL=$env:DATABASE_URL
        $env:ML_REQUIRE_AUTH='true'
        & .venv/Scripts/python.exe -m uvicorn sanket_ml.inference.api:app --host 127.0.0.1 --port 8001 *> (Join-Path $PSScriptRoot 'demo-ml.log')
    }
    'frontend' {
        Set-Location (Join-Path $repoRoot 'frontend')
        $env:VITE_API_BASE_URL='http://127.0.0.1:8010/api/v1'
        $env:VITE_WS_BASE_URL='ws://127.0.0.1:8010'
        npm run dev -- --host 127.0.0.1 *> (Join-Path $PSScriptRoot 'demo-frontend.log')
    }
}
