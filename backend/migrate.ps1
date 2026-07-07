<#
.SYNOPSIS
    Dev convenience wrapper for Alembic migrations.

.DESCRIPTION
    The deploy pipeline runs 'alembic upgrade head' automatically, but local dev
    DBs do not, so pulling new migrations leaves the DB behind until you run them
    by hand. This script does that (and a few other common ops) without having to
    remember the venv path.

.EXAMPLE
    .\migrate.ps1            # upgrade to head (default)
    .\migrate.ps1 status     # show current revision vs. head
    .\migrate.ps1 history    # list migrations
#>
param(
    [ValidateSet("upgrade", "status", "history")]
    [string]$Command = "upgrade"
)

$ErrorActionPreference = "Stop"
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

# In local development, the app runs as 'sanket_app' which lacks DDL privileges.
# We run migrations as the 'postgres' superuser to avoid 'permission denied' errors.
if (-not $env:MIGRATION_DATABASE_URL) {
    $env:MIGRATION_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/sanket"
}

if (-not (Test-Path $py)) {
    Write-Error "venv python not found at $py - create the backend venv first."
    exit 1
}

Push-Location $PSScriptRoot
try {
    switch ($Command) {
        "upgrade" { & $py -m alembic upgrade head }
        "status"  { & $py -m alembic current; & $py -m alembic heads }
        "history" { & $py -m alembic history }
    }
}
finally {
    Pop-Location
}
