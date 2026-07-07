@echo off
title Rebuilding SANKET backend...
cd /d C:\Users\admin\Desktop\Sanket
echo Rebuilding backend container to pick up integrations_hub router...
docker compose up -d --build backend
echo.
echo Done. Backend should be available at http://localhost:8000 in ~30s
pause
