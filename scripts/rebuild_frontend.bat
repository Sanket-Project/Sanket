@echo off
title Sanket — Rebuild Frontend
cd /d C:\Users\admin\Desktop\Sanket
echo Rebuilding frontend container (Vite build + nginx)...
echo This takes about 60-90 seconds.
echo.
docker compose up -d --build frontend
echo.
echo Done. Refresh http://localhost:8080 in Chrome.
pause
