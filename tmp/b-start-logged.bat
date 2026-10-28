@echo off
cd /d "%~dp0.."
call scripts\start-dev.bat > "%~dp0start-logged.log" 2>&1
echo EXIT=%errorlevel% >> "%~dp0start-logged.log"
