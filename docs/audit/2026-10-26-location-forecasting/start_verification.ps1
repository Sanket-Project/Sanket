param([ValidateSet('api','ml')][string]$Service)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$env:DATABASE_URL = 'postgresql+asyncpg://sanket_app:changeme@127.0.0.1:55434/sanket'
$env:REDIS_URL = ''
$env:JWT_SECRET = 'synthetic-location-verification-only-2026'
$env:FIREBASE_PROJECT_ID = ''
$env:FIREBASE_CREDENTIALS_PATH = ''
$env:FIREBASE_WEB_API_KEY = ''
$env:ML_API_URL = 'http://127.0.0.1:8013'
$env:ML_SERVICE_TOKEN = 'synthetic-location-verification-local'
$env:SIGNAL_PIPELINE_ENABLED = 'false'
$env:SHOPIFY_POLL_ENABLED = 'false'
$env:WHATSAPP_DIGEST_WORKER_ENABLED = 'false'
$env:PUBLIC_SIGNUP_ENABLED = 'true'
if ($Service -eq 'api') {
    $work = Join-Path $repoRoot 'backend'
    $module = 'app.main:app'
    $port = 8012
} else {
    $work = Join-Path $repoRoot 'backend/ml'
    $env:ML_DATABASE_URL = 'postgresql://sanket_app:changeme@127.0.0.1:55434/sanket'
    $env:ML_DATABASE_ASYNC_URL = $env:DATABASE_URL
    $env:ML_REQUIRE_AUTH = 'true'
    $env:ML_CHRONOS_PRELOAD_ON_STARTUP = 'false'
    $module = 'sanket_ml.inference.api:app'
    $port = 8013
}
if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
    throw "Port $port is already occupied"
}
$proc = Start-Process -FilePath (Join-Path $work '.venv/Scripts/python.exe') -WindowStyle Hidden `
    -WorkingDirectory $work -ArgumentList @('-m','uvicorn',$module,'--host','127.0.0.1','--port',"$port") `
    -RedirectStandardOutput (Join-Path $PSScriptRoot "$Service.stdout.log") `
    -RedirectStandardError (Join-Path $PSScriptRoot "$Service.stderr.log") -PassThru
Write-Output "$Service PID=$($proc.Id) port=$port"
