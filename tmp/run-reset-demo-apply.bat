@echo off
cd /d "%~dp0.."
set LOG=%~dp0reset-demo-apply.log
set DUMP=sanket_recovered_20261026_pre_demo_reset3.dump
docker compose exec -T postgres pg_dump -U postgres -d sanket_recovered_20261026 -Fc -f /tmp/%DUMP% > "%LOG%" 2>&1
if errorlevel 1 ( echo BACKUP FAILED - nothing changed >> "%LOG%" & exit /b 1 )
docker compose cp postgres:/tmp/%DUMP% "%~dp0..\backups\%DUMP%" >> "%LOG%" 2>&1
if errorlevel 1 ( echo BACKUP COPY FAILED - nothing changed >> "%LOG%" & exit /b 1 )
for /f "tokens=1,* delims==" %%a in ('findstr /b "POSTGRES_SUPERUSER_PASSWORD=" .env') do set PGSU=%%b
set MIGRATION_DATABASE_URL=postgresql+asyncpg://postgres:%PGSU%@localhost:5432/sanket_recovered_20261026
cd backend
set PYTHONPATH=%CD%
.venv\Scripts\python.exe ..\tmp\reset_demo.py apply >> "%LOG%" 2>&1
echo EXIT=%errorlevel% >> "%LOG%"
