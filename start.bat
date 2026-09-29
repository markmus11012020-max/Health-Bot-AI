@echo off
REM ============================================================================
REM Health-Bot-AI — Windows deploy script
REM Pipeline: stop old processes -> clear cache -> build env -> install deps
REM ============================================================================
setlocal EnableDelayedExpansion

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

set "VENV_DIR=%PROJECT_DIR%venv"
set "PYTHON=python"

echo ============================================================
echo  Health-Bot-AI — Windows auto-deploy
echo  Project dir: %PROJECT_DIR%
echo ============================================================
echo.

REM ---- 1. Stop old processes (Streamlit / uvicorn leftovers) ----
echo [1/4] Stopping old processes...
taskkill /F /IM streamlit.exe /T >nul 2>&1
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Health-Bot-AI*" /T >nul 2>&1
if errorlevel 1 (
    echo   No old processes found.
) else (
    echo   Old processes terminated.
)
echo.

REM ---- 2. Clear cache ----
echo [2/4] Clearing bytecode / cache...
if exist "%PROJECT_DIR%__pycache__" (
    rd /s /q "%PROJECT_DIR%__pycache__"
)
if exist "%PROJECT_DIR%src\__pycache__" rd /s /q "%PROJECT_DIR%src\__pycache__"
if exist "%PROJECT_DIR%tests\__pycache__" rd /s /q "%PROJECT_DIR%tests\__pycache__"
if exist "%PROJECT_DIR%config\__pycache__" rd /s /q "%PROJECT_DIR%config\__pycache__"
for /d /r "%PROJECT_DIR%" %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
for /r "%PROJECT_DIR%" %%f in (*.pyc) do @if exist "%%f" del /q "%%f"
if exist "%PROJECT_DIR%.pytest_cache" rd /s /q "%PROJECT_DIR%.pytest_cache"
if exist "%PROJECT_DIR%.streamlit\cache" rd /s /q "%PROJECT_DIR%.streamlit\cache"
echo   Cache cleared.
echo.

REM ---- 3. Build virtual env + install deps ----
echo [3/4] Preparing virtual environment...
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo   Creating venv...
    "%PYTHON%" -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo   ERROR: failed to create venv. Ensure Python 3.10+ is on PATH.
        exit /b 1
    )
) else (
    echo   Reusing existing venv.
)

set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"

echo   Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip --quiet
if errorlevel 1 (
    echo   WARNING: pip upgrade failed, continuing.
)

if exist "%PROJECT_DIR%requirements.txt" (
    echo   Installing dependencies from requirements.txt...
    "%VENV_PIP%" install -r "%PROJECT_DIR%requirements.txt" --quiet
    if errorlevel 1 (
        echo   ERROR: dependency installation failed.
        exit /b 1
    )
) else (
    echo   WARNING: requirements.txt not found.
)
echo   Dependencies installed.
echo.

REM ---- 4. Launch Streamlit ----
echo [4/4] Launching Streamlit on port 8501...
if not exist "%PROJECT_DIR%.env" (
    if exist "%PROJECT_DIR%.env.example" (
        echo   WARNING: .env missing, copying from .env.example ^(placeholder keys^)
        copy /y "%PROJECT_DIR%.env.example" "%PROJECT_DIR%.env" >nul
    ) else (
        echo   WARNING: no .env found. App will start with default placeholders.
    )
)

title Health-Bot-AI (Streamlit)
"%VENV_PY%" -m streamlit run "%PROJECT_DIR%app.py" --server.port=8501 --server.headless=false

endlocal