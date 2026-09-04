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
    echo  Make sure to tick "Add Git to PATH" during install.
    echo.
    pause
    exit /b 1
)

:: Check if this folder is already a git repo
git rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
    echo  This folder is not a git repository.
    echo  That usually means the project was downloaded as a ZIP
    echo  instead of cloned. We'll fix that now.
    echo.
    echo  Initialising git and connecting to the remote...
    echo.

    git init
    git remote add origin https://github.com/bluefire4691/project-genesis.git
    git fetch origin claude/extract-genesis-repo-fn5vW
    git checkout -b claude/extract-genesis-repo-fn5vW --track origin/claude/extract-genesis-repo-fn5vW

    if errorlevel 1 (
        echo.
        echo  Setup failed. Try cloning manually:
        echo    git clone -b claude/extract-genesis-repo-fn5vW https://github.com/bluefire4691/project-genesis.git
        echo.
        pause
        exit /b 1
    )

    echo.
    echo  Repository connected. Genesis is up to date.
    echo  Close this window and launch Genesis normally.
    echo.
    pause
    exit /b 0
)

echo  Pulling latest changes...
echo.
git pull origin claude/extract-genesis-repo-fn5vW

echo.
echo  Done. Close this window and launch Genesis normally.
echo.
pause
