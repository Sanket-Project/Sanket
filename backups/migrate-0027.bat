@echo off
setlocal
cd /d "%~dp0.."
set LOG=%~dp0migrate-0027.log
set DB=sanket_recovered_20261026
set DUMP=sanket_recovered_20261026_pre0027.dump
for /f "tokens=1,* delims==" %%a in ('findstr /b "POSTGRES_SUPERUSER_PASSWORD=" .env') do set PGSU=%%b
echo === backup %DATE% %TIME% > "%LOG%"
docker compose exec -T postgres pg_dump -U postgres -d %DB% -Fc -f /tmp/%DUMP% >> "%LOG%" 2>&1
if errorlevel 1 ( echo BACKUP FAILED - migration not run >> "%LOG%" & exit /b 1 )
docker compose cp postgres:/tmp/%DUMP% "%~dp0%DUMP%" >> "%LOG%" 2>&1
if errorlevel 1 ( echo BACKUP COPY FAILED - migration not run >> "%LOG%" & exit /b 1 )
echo === migrate >> "%LOG%"
set MIGRATION_DATABASE_URL=postgresql+asyncpg://postgres:%PGSU%@localhost:5432/%DB%
cd backend
.venv\Scripts\python.exe -m alembic current >> "%LOG%" 2>&1
.venv\Scripts\python.exe -m alembic upgrade head >> "%LOG%" 2>&1
echo UPGRADE_EXIT=%errorlevel% >> "%LOG%"
.venv\Scripts\python.exe -m alembic current >> "%LOG%" 2>&1
