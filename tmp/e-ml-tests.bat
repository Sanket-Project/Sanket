@echo off
cd /d "%~dp0..\backend\ml"
.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider > "%~dp0zz-ml-tests.log" 2>&1
echo EXIT=%errorlevel% >> "%~dp0zz-ml-tests.log"
