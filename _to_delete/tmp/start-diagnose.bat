@echo off
cd /d "%~dp0.."
call scripts\start-dev.bat --no-open-browser > "%~dp0start-diagnose.log" 2>&1
echo EXIT=%errorlevel% >> "%~dp0start-diagnose.log"
