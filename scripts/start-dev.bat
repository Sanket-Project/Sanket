@echo off
setlocal
cd /d "%~dp0..\backend"
where uv >nul 2>&1
if errorlevel 1 (
    echo uv is required. Install uv, then retry.
    exit /b 1
)
uv run python -m scripts.dev_stack %*
exit /b %errorlevel%
