@echo off
title Genesis - Start Local LLM
cd /d "%~dp0"

rem Installs and starts a local model server automatically.
rem No manual downloads, no environment variables to set.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_llm.ps1" %*

if errorlevel 1 (
    echo.
    echo  Setup did not complete - see the message above.
    echo.
)
pause
