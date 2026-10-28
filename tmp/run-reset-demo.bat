@echo off
cd /d "%~dp0..\backend"
set PYTHONPATH=%CD%
.venv\Scripts\python.exe ..\tmp\reset_demo.py %* > "%~dp0reset-demo.log" 2>&1
echo EXIT=%errorlevel% >> "%~dp0reset-demo.log"
