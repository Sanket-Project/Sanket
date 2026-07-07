@echo off
REM =========================================================================
REM  SANKET - one-command local dev startup
REM  Opens separate terminal windows: backend API, worker, ML API, frontend.
REM  Optionally starts PostgreSQL via Docker if it's not already running.
REM =========================================================================

setlocal
set "ROOT=%~dp0..\"
cd /d "%ROOT%"

echo.
echo  ===========================================================
echo                SANKET - local dev startup
echo  ===========================================================
echo.

REM -- 1. PostgreSQL --------------------------------------------------------
echo  [1/5] Checking PostgreSQL on port 5432...
netstat -an | findstr ":5432" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo        Not running. Trying docker compose up -d postgres...
    where docker >nul 2>&1
    if errorlevel 1 (
        echo        WARNING: Docker is not installed. Start PostgreSQL manually
        echo                 before continuing, or install Docker Desktop.
        echo                 Required: db "sanket", user "sanket_app".
        pause
    ) else (
        docker compose up -d postgres
        echo        Waiting 8s for Postgres to accept connections...
        timeout /t 8 /nobreak >nul
    )
) else (
    echo        OK - already listening.
)

REM -- 2. Backend API (port 8000) -------------------------------------------
echo  [2/5] Launching backend API ........... http://localhost:8000/docs
start "SANKET backend :8000" cmd /k "cd /d "%ROOT%backend" && (if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat) && python -m uvicorn app.main:app --reload --port 8000"

REM -- 3. Background Worker -------------------------------------------------
echo  [3/5] Launching background worker ...... arq forecast worker
start "SANKET worker" cmd /k "cd /d "%ROOT%backend" && (if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat) && python -m arq app.workers.forecast_worker.WorkerSettings"

REM -- 4. ML Inference API (port 8001) --------------------------------------
echo  [4/5] Launching ML inference .......... http://localhost:8001/health
start "SANKET ml-api :8001" cmd /k "cd /d "%ROOT%backend\ml" && (if exist venv\Scripts\activate.bat (call venv\Scripts\activate.bat) else (if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat)) && python -m uvicorn sanket_ml.inference.api:app --reload --port 8001"

REM -- 5. Frontend (port 5173) ----------------------------------------------
echo  [5/5] Launching frontend .............. http://localhost:5173
start "SANKET frontend :5173" cmd /k "cd /d "%ROOT%frontend" && npm run dev"

echo.
echo  ===========================================================
echo    All services starting in separate windows.
echo.
echo      Frontend  =^>  http://localhost:5173
echo      Backend   =^>  http://localhost:8000/docs
echo      ML API    =^>  http://localhost:8001/health
echo      Worker    =^>  arq background worker
echo.
echo    Close any service window to stop just that service,
echo    or run stop-dev.bat to kill all of them.
echo  ===========================================================
echo.

endlocal
