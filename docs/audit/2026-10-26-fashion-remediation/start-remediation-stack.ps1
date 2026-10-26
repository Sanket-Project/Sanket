param([ValidateSet('all','api','ml','frontend','migrate','seed')][string]$Mode='all')
$ErrorActionPreference='Stop'
$repoRoot=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$env:DATABASE_URL='postgresql+asyncpg://sanket_app:remediation-local@127.0.0.1:55433/sanket'
$env:REDIS_URL='redis://127.0.0.1:56380/0'
$env:ML_API_URL='http://127.0.0.1:8002'
$env:ML_SERVICE_TOKEN='synthetic-remediation-local'
$env:JWT_SECRET='synthetic-remediation-local-test-secret-2026'
$env:FIREBASE_PROJECT_ID=''
$env:FIREBASE_CREDENTIALS_PATH=''
$env:FIREBASE_WEB_API_KEY=''
$env:SIGNAL_PIPELINE_ENABLED='false'
$env:SHOPIFY_POLL_ENABLED='false'
$env:WHATSAPP_DIGEST_WORKER_ENABLED='false'
$env:CORS_ORIGINS='["http://127.0.0.1:5174","http://localhost:5174"]'
if ($Mode -eq 'all') {
    foreach ($entry in @(@('sanket-remediation-db','55433:5432','pgvector/pgvector:pg16'),@('sanket-remediation-redis','56380:6379','redis:7-alpine'))) {
        docker inspect $entry[0] *> $null
        if ($LASTEXITCODE -eq 0) { docker start $entry[0] | Out-Null }
        elseif ($entry[0] -eq 'sanket-remediation-db') {
            docker run -d --name $entry[0] -e POSTGRES_PASSWORD=remediation-local -e POSTGRES_DB=sanket -p $entry[1] $entry[2]
        } else { docker run -d --name $entry[0] -p $entry[1] $entry[2] }
        if ($LASTEXITCODE -ne 0) { throw 'Container startup failed' }
    }
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        docker exec sanket-remediation-db pg_isready -U postgres *> $null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 1
    }
    & $PSCommandPath -Mode migrate
    $shellPath=(Get-Process -Id $PID).Path
    foreach ($service in @('api','ml','frontend')) {
        $port=@{api=8011;ml=8002;frontend=5174}[$service]
        if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { throw "Port $port already in use; verify its owner before reusing the running stack." }
        Start-Process -FilePath $shellPath -WindowStyle Hidden -ArgumentList @('-NoProfile','-File',('"'+$PSCommandPath+'"'),'-Mode',$service)
    }
    Write-Output 'SYNTHETIC remediation stack: http://127.0.0.1:5174. Run -Mode seed once API and ML health pass.'
    return
}
switch ($Mode) {
    'migrate' {
        Set-Location (Join-Path $repoRoot 'backend')
        $env:MIGRATION_DATABASE_URL='postgresql+asyncpg://postgres:remediation-local@127.0.0.1:55433/sanket'
        $migrationLog=Join-Path $PSScriptRoot 'fresh-migration.log'
        if (Test-Path -LiteralPath $migrationLog) { $migrationLog=Join-Path $PSScriptRoot ('migration-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'.log') }
        & .venv/Scripts/python.exe -m alembic upgrade head *> $migrationLog
        if ($LASTEXITCODE -ne 0) { throw 'Migration failed; inspect fresh-migration.log' }
        docker exec sanket-remediation-db psql -U postgres -d sanket -c "ALTER ROLE sanket_app PASSWORD 'remediation-local'"
        if ($LASTEXITCODE -ne 0) { throw 'Application role setup failed' }
        Remove-Item Env:MIGRATION_DATABASE_URL
    }
    'seed' {
        Set-Location (Join-Path $repoRoot 'backend')
        & .venv/Scripts/python.exe -m scripts.seed_remediation_fixture --db-port 55433
        if ($LASTEXITCODE -ne 0) { throw 'Synthetic fixture setup failed' }
    }
    'api' {
        Set-Location (Join-Path $repoRoot 'backend')
        & .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011 *> (Join-Path $PSScriptRoot 'remediation-api.log')
    }
    'ml' {
        Set-Location (Join-Path $repoRoot 'backend/ml')
        $env:ML_DATABASE_URL='postgresql://sanket_app:remediation-local@127.0.0.1:55433/sanket'
        $env:ML_DATABASE_ASYNC_URL=$env:DATABASE_URL
        $env:ML_DEVICE='cpu'
        $env:ML_CHRONOS_REPO='amazon/chronos-t5-small'
        $env:ML_TORCH_NUM_THREADS='4'
        $env:OMP_NUM_THREADS='4'
        $env:MKL_NUM_THREADS='4'
        $env:ML_ZERO_SHOT_NUM_SAMPLES='100'
        $env:ML_REQUIRE_AUTH='true'
        & .venv/Scripts/python.exe -m uvicorn sanket_ml.inference.api:app --host 127.0.0.1 --port 8002 *> (Join-Path $PSScriptRoot 'remediation-ml.log')
    }
    'frontend' {
        Set-Location (Join-Path $repoRoot 'frontend')
        $env:VITE_API_BASE_URL='/api/v1'
        $env:VITE_PROXY_TARGET='http://127.0.0.1:8011'
        $env:VITE_WS_BASE_URL='ws://127.0.0.1:8011'
        npm run dev -- --host 127.0.0.1 --port 5174 --strictPort *> (Join-Path $PSScriptRoot 'remediation-frontend.log')
    }
}
