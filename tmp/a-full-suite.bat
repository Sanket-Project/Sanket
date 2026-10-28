@echo off
cd /d "%~dp0..\backend"
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider > "%~dp0zz-full-suite.log" 2>&1
echo EXIT=%errorlevel% >> "%~dp0zz-full-suite.log"
