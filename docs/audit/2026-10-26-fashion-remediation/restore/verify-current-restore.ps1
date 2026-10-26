# Read-only backup of the synthetic audit; restore only to the dedicated 55434 container.
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../../..')).Path
$sourceContainer = 'sanket-remediation-db'
$targetContainer = 'sanket-remediation-restore-db'
function Check-Native([string]$operation) {
    if ($LASTEXITCODE -ne 0) { throw "$operation failed (exit $LASTEXITCODE)" }
}
$empty = docker exec $targetContainer psql -U postgres -d sanket -Atc "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
Check-Native 'Target inspection'
if ([int]$empty -ne 0) { throw 'Restore target is not empty; refusing to overwrite it' }
$metricsSql = @'
SELECT json_build_object(
  'revision',(SELECT version_num FROM alembic_version),
  'tenants',(SELECT count(*) FROM tenants),
  'skus',(SELECT count(*) FROM skus),
  'sales_rows',(SELECT count(*) FROM historical_sales),
  'units',(SELECT coalesce(sum(units_sold),0) FROM historical_sales),
  'forecast_runs',(SELECT count(*) FROM forecast_runs),
  'forecast_results',(SELECT count(*) FROM forecast_results),
  'inventory_rows',(SELECT count(*) FROM inventory_levels),
  'recommendations',(SELECT count(*) FROM recommendations))::text
'@
$before = docker exec -e 'PGOPTIONS=-c default_transaction_read_only=on' $sourceContainer psql -U postgres -d sanket -Atc $metricsSql
Check-Native 'Read-only source metrics'
$before | Set-Content (Join-Path $PSScriptRoot 'current-source-counts.json')
docker exec -e 'PGOPTIONS=-c default_transaction_read_only=on' $sourceContainer pg_dump -U postgres -d sanket -Fc --file=/tmp/remediation-readonly.dump
Check-Native 'Read-only pg_dump'
$dumpPath = Join-Path $PSScriptRoot 'current-audit.dump'
docker cp "${sourceContainer}:/tmp/remediation-readonly.dump" $dumpPath
Check-Native 'Backup copy'
docker cp $dumpPath "${targetContainer}:/tmp/remediation-readonly.dump"
Check-Native 'Restore copy'
docker exec $targetContainer pg_restore -U postgres -d sanket --exit-on-error /tmp/remediation-readonly.dump
Check-Native 'pg_restore'
$env:MIGRATION_DATABASE_URL = 'postgresql+asyncpg://postgres:remediation-restore-local@127.0.0.1:55434/sanket'
Push-Location (Join-Path $repoRoot 'backend')
try {
    & .venv/Scripts/python.exe -m alembic upgrade head *> (Join-Path $PSScriptRoot 'current-upgrade.log')
    Check-Native 'Restored database migrations'
} finally { Pop-Location; Remove-Item Env:MIGRATION_DATABASE_URL }
$after = docker exec $targetContainer psql -U postgres -d sanket -Atc $metricsSql
Check-Native 'Restored metrics'
$after | Set-Content (Join-Path $PSScriptRoot 'current-restored-counts.json')
if ($before -ne $after) { throw 'Source/restore counts differ; inspect JSON metrics' }
$role = docker exec $targetContainer psql -U postgres -d sanket -Atc "SELECT rolsuper::text || '|' || rolbypassrls::text FROM pg_roles WHERE rolname='sanket_app'"
Check-Native 'Application role flags'
if ($role -ne 'false|false') { throw 'Application role has excess privileges' }
$tenantId = docker exec $targetContainer psql -U postgres -d sanket -Atc "SELECT id FROM tenants WHERE slug='synthetic-remediation'"
Check-Native 'Synthetic tenant lookup'
$tenantId = ([guid]::Parse($tenantId)).ToString()
$ownerCount = docker exec $targetContainer psql -U postgres -d sanket -Atc "SELECT count(*) FROM historical_sales WHERE tenant_id='$tenantId'"
Check-Native 'Owner count'
$unscoped = docker exec -e PGPASSWORD=remediation-restore-local $targetContainer psql -h 127.0.0.1 -U sanket_app -d sanket -Atc "SELECT count(*) FROM historical_sales"
Check-Native 'Unscoped application read'
$scoped = docker exec -e PGPASSWORD=remediation-restore-local $targetContainer psql -h 127.0.0.1 -U sanket_app -d sanket -Atc "SELECT set_config('app.current_tenant_id','$tenantId',true); SELECT count(*) FROM historical_sales"
Check-Native 'Tenant application read'
$foreignId = [guid]::NewGuid().ToString()
$foreign = docker exec -e PGPASSWORD=remediation-restore-local $targetContainer psql -h 127.0.0.1 -U sanket_app -d sanket -Atc "SELECT set_config('app.current_tenant_id','$foreignId',true); SELECT count(*) FROM historical_sales"
Check-Native 'Other tenant application read'
if ([int]$unscoped -ne 0 -or [int]$scoped[-1] -ne [int]$ownerCount -or [int]$foreign[-1] -ne 0) { throw 'Restored RLS isolation failed' }
@{
    synthetic_only = $true
    source_port = 55433
    restore_port = 55434
    source_backup_read_only = $true
    matching_counts = $true
    revision = ($after | ConvertFrom-Json).revision
    application_role_superuser = $false
    application_role_bypassrls = $false
    unscoped_sales_visible = [int]$unscoped
    own_tenant_sales_visible = [int]$scoped[-1]
    other_tenant_sales_visible = [int]$foreign[-1]
    dump_sha256 = (Get-FileHash -LiteralPath $dumpPath -Algorithm SHA256).Hash
    original_pre_fix_audit_database_available = $false
} | ConvertTo-Json | Set-Content (Join-Path $PSScriptRoot 'current-restore-verification.json')
Write-Output 'Read-only backup, restore, migrations, reconciliation and RLS checks passed.'
