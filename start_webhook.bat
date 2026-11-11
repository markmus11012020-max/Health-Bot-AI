@echo off
REM ============================================================================
REM Health-Bot-AI — Webhook/API server (FastAPI)
REM Production MVP: no --reload; use docker-compose for production.
REM ============================================================================
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

set "VENV_PY=%PROJECT_DIR%venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo ERROR: venv not found. Run start.bat first.
    exit /b 1
)

if not exist "%PROJECT_DIR%.env" (
    if exist "%PROJECT_DIR%.env.example" (
        echo WARNING: .env missing, copying from .env.example ^(placeholder keys^)
        copy /y "%PROJECT_DIR%.env.example" "%PROJECT_DIR%.env" >nul
    )
)

echo.
echo Starting Health-Bot-AI API on http://localhost:8080
echo Docs:  http://localhost:8080/docs
echo Health: http://localhost:8080/health
echo Ready:  http://localhost:8080/ready
echo.

title Health-Bot-AI (API)
"%VENV_PY%" -m uvicorn src.api.webhook:app --host 0.0.0.0 --port 8080

endlocal
