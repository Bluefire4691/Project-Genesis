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

:: Install GUI dependencies if missing (one-time)
python -c "import PyQt6" >nul 2>&1 || (
    echo  Installing desktop GUI dependencies ^(PyQt6 + matplotlib^)...
    pip install PyQt6 matplotlib >nul 2>&1
)

echo  Starting Genesis desktop window...
echo.

chcp 65001 > nul
python src\gui.py --resume --self-directed --speed 8 --batch 10

echo.
echo  Genesis session ended.
pause
