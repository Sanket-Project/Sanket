@echo off
title Sanket — Bulk Sales Ingest
cd /d C:\Users\admin\Desktop\Sanket
echo Installing psycopg2-binary...
pip install psycopg2-binary --quiet
echo.
echo Running ingestion script...
python scripts\ingest_sales.py
echo.
pause
