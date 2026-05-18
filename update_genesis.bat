@echo off
title Genesis - Update
color 0B

echo.
echo  ==========================================
echo    PROJECT GENESIS - Update
echo  ==========================================
echo.

cd /d "%~dp0"

:: Check git is installed
git --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Git not found.
    echo  Install Git from https://git-scm.com
    echo.
    pause
    exit /b 1
)

echo  Pulling latest changes...
echo.
git pull origin claude/extract-genesis-repo-fn5vW

echo.
echo  Done. Close this window and launch Genesis normally.
echo.
pause
