@echo off
cd /d "%~dp0..\backend"
.venv\Scripts\python.exe -m pytest tests/test_allocation.py -q -p no:cacheprovider > "%~dp0zz-allocation.log" 2>&1
echo EXIT=%errorlevel% >> "%~dp0zz-allocation.log"
