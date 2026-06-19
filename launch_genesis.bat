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

:: Make sure the UI library is present (one-time, only installs if missing)
python -c "import rich" >nul 2>&1 || (
    echo  First run of the new UI - installing 'rich' ^(once^)...
    pip install rich >nul 2>&1
)

echo  Starting Genesis... resuming previous session.
echo.
echo  Genesis thinks and learns continuously in the background.
echo  This single window stays clean: you only see what it chooses
echo  to express, plus a quiet status line every 30 seconds.
echo.
echo  Just type to talk. Useful commands:
echo    speed N     give it more CPU   (1 = gentle, 10 = full tilt)
echo    memory N    wider attention    (more concepts held at once)
echo    fetch N     read more per cycle
echo    explore     break out of a topic it's stuck on
echo    reflect     make it consolidate now
echo    status      where it's at      ^|   quit   save and exit
echo.

chcp 65001 > nul
python src\ui.py --resume --self-directed

echo.
echo  Genesis session ended.
pause
