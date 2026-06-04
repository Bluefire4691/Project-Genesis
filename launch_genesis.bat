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
echo  Genesis will think and learn continuously.
echo.
echo  TWO windows will open:
echo    - THIS window: talk to Genesis (just type).
echo    - "Genesis - Live Thoughts": watch it think and learn.
echo  Type anything to talk. Use /quit to exit.
echo.

:: Make sure the thoughts log exists, then open a second window that streams it.
:: This is Genesis's "stream of thought" — it runs alongside the conversation
:: window so the thinking never floods the place where you type.
if not exist data mkdir data
if not exist data\genesis_thoughts.log type nul > data\genesis_thoughts.log
start "Genesis - Live Thoughts" powershell -NoExit -Command "Get-Content -Path 'data\genesis_thoughts.log' -Wait -Tail 40"

python src/main.py --open-only --resume --live

echo.
echo  Genesis session ended.
pause
