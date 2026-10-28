@echo off
cd /d "%~dp0..\backend\ml"
for /f "tokens=1,* delims==" %%a in ('findstr /b "DATABASE_URL=" ..\.env') do set DBURL=%%b
set ML_DATABASE_URL=%DBURL:postgresql+asyncpg=postgresql%
set ML_DATABASE_ASYNC_URL=%DBURL%
set PYTHONPATH=%CD%
set ML_DEVICE=cpu
set ML_CHRONOS_REPO=amazon/chronos-t5-small
set LOG=%~dp0zz-ml-repro.log
echo === defaults after fix > "%LOG%"
.venv\Scripts\python.exe -X faulthandler ..\..\tmp\ml_repro.py >> "%LOG%" 2>&1
echo EXIT=%errorlevel% >> "%LOG%"
