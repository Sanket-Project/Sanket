@echo off
REM Closes the three SANKET dev windows by their titles.

echo Stopping SANKET dev services...
taskkill /FI "WINDOWTITLE eq SANKET backend :8000*"  /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq SANKET ml-api :8001*"   /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq SANKET worker*"          /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq SANKET frontend :5173*" /F >nul 2>&1
echo Done.
