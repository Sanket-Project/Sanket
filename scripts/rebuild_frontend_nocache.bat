@echo off
title Sanket — Rebuild Frontend (no cache)
cd /d C:\Users\admin\Desktop\Sanket
echo Force-rebuilding frontend (bypassing Docker cache)...
echo This takes about 90-120 seconds.
echo.
docker compose build --no-cache frontend
docker compose up -d frontend
echo.
echo Done. Refresh http://localhost:8080 in Chrome.
pause
