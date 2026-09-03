@echo off
title Genesis - Set up llama.cpp + model
cd /d "%~dp0"

rem Thin launcher. All logic lives in the .ps1 -- inlining PowerShell in a
rem batch file needs caret continuations and nested quote escaping, which is
rem fragile and breaks outright on paths containing spaces.
rem
rem Pass-through examples:
rem     setup_llamacpp.bat -Backend cpu
rem     setup_llamacpp.bat -SkipServer

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_llamacpp.ps1" %*

if errorlevel 1 (
    echo.
    echo  Setup did not complete. Read the message above - it names the fix.
    echo.
)
pause
