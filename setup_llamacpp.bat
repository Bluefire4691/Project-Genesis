@echo off
title Genesis - Set up llama.cpp + model
setlocal

rem Thin launcher. All logic lives in the .ps1 -- inlining PowerShell in a
rem batch file needs caret continuations and nested quote escaping, which is
rem fragile and breaks outright on paths containing spaces.
rem
rem NOTE: start_llm.bat is the easier path. This one is for pinning a
rem specific llama.cpp backend (board 0.2b benchmarking).
rem
rem Pass-through examples:
rem     setup_llamacpp.bat -Backend rocm
rem     setup_llamacpp.bat -Backend cpu
rem     setup_llamacpp.bat -SkipServer

set "PS1="
if exist "%~dp0setup_llamacpp.ps1"     set "PS1=%~dp0setup_llamacpp.ps1"
if not defined PS1 if exist "%~dp0..\setup_llamacpp.ps1" set "PS1=%~dp0..\setup_llamacpp.ps1"
if not defined PS1 if exist "%CD%\setup_llamacpp.ps1"    set "PS1=%CD%\setup_llamacpp.ps1"

if not defined PS1 (
    echo.
    echo  ERROR: setup_llamacpp.ps1 not found.
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
    echo  Setup did not complete. Read the message above - it names the fix.
    echo.
)
pause
