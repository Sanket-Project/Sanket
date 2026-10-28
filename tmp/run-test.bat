@echo off
cd /d "%~dp0..\backend"
.venv\Scripts\python.exe -m pytest %* > "%~dp0run-test.log" 2>&1
echo EXIT=%errorlevel% >> "%~dp0run-test.log"
