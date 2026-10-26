@echo off
REM =========================================================================
REM  SANKET - one-command local dev startup from root directory
REM =========================================================================
cd /d "%~dp0"
call scripts\start-dev.bat
REM Keep a failed start on screen; a double-clicked window would otherwise close.
if errorlevel 1 pause
