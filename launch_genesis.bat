@echo off
title Project Genesis
color 0A

echo.
echo  ==========================================
echo    PROJECT GENESIS
echo  ==========================================
echo.

:: Move into the project-genesis subfolder (next to this file)
cd /d "%~dp0project-genesis"

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found.
    echo  Install Python 3.10+ from https://python.org
    echo  Make sure to tick "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

echo  Starting Genesis... resuming previous session.
echo  Type  help  at the prompt for available commands.
echo  Type  quit  to exit.
echo.

python src/main.py --open-only --resume --interactive --self-directed

echo.
echo  Genesis session ended.
pause
