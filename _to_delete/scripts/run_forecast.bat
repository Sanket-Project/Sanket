@echo off
title Sanket — Forecast Generation
cd /d C:\Users\admin\Desktop\Sanket
echo Installing dependencies...
pip install pyjwt requests --quiet
echo.
echo Running forecast generation (may take a few minutes for Chronos on CPU)...
python scripts\run_forecast.py
echo.
pause
