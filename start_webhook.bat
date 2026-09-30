@echo off
REM ============================================================================
REM Health-Bot-AI — Webhook-сервер (FastAPI)
REM Запускает FastAPI webhook на порту 8080 для интеграции с AmoCRM и др.
REM ============================================================================
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

set "VENV_PY=%PROJECT_DIR%venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo ERROR: venv not found. Run start.bat first.
    exit /b 1
)

echo.
echo Starting Health-Bot-AI webhook on http://localhost:8080
echo Docs:  http://localhost:8080/docs
echo.

title Health-Bot-AI (Webhook)
"%VENV_PY%" -m uvicorn src.api.webhook:app --host 0.0.0.0 --port 8080 --reload

endlocal