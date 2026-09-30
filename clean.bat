@echo off
REM Cross-platform Python bytecode cache cleaner for Health-Bot-AI.
REM
REM Usage:
REM   clean.bat           - actually delete __pycache__/ and *.pyc files
REM   clean.bat --dry-run - show what would be removed, don't touch anything
REM
REM Requires Python on PATH (the venv is preferred when active).

setlocal
pushd "%~dp0"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PY=python"
    ) else (
        echo [clean] Python not found on PATH. Activate your venv or install Python 3.10+.
        popd
        exit /b 2
    )
)

%PY% scripts\clean_cache.py %*
set "RC=%ERRORLEVEL%"

popd
endlocal & exit /b %RC%
