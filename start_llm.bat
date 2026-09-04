@echo off
title Genesis - Start Local LLM
setlocal

rem Installs and starts a local model server automatically.
rem No manual downloads, no environment variables to set.
rem
rem Location-proof: finds start_llm.ps1 whether this .bat sits at the repo
rem root or one level down, so a copy in the wrong folder still works.

set "PS1="
if exist "%~dp0start_llm.ps1"    set "PS1=%~dp0start_llm.ps1"
if not defined PS1 if exist "%~dp0..\start_llm.ps1" set "PS1=%~dp0..\start_llm.ps1"
if not defined PS1 if exist "%CD%\start_llm.ps1"    set "PS1=%CD%\start_llm.ps1"

if not defined PS1 (
    echo.
    echo  ERROR: start_llm.ps1 not found.
    echo.
    echo  Looked in:
    echo    %~dp0
    echo    %~dp0..\
    echo    %CD%\
    echo.
    echo  Run update_genesis.bat to pull the latest files, then try again.
    echo.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*

if errorlevel 1 (
    echo.
    echo  Setup did not complete - see the message above.
    echo.
)
pause
