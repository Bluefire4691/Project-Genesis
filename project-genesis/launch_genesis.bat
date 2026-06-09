@echo off
rem Genesis Windows Launcher
rem Opens two windows: live thoughts (read-only) + conversation.
rem
rem Usage:
rem   launch_genesis.bat               -- resume last session (default)
rem   launch_genesis.bat --open-only   -- skip curriculum, start at OPEN
rem   launch_genesis.bat --cycles 200  -- run longer before entering live mode
rem
rem Requirements: Python 3.9+ on PATH, pip install -r requirements.txt

chcp 65001 > nul

rem Make sure the data directory exists so the thought log can be created
if not exist "data" mkdir data

rem Open the live-thoughts window in a new terminal
start "Genesis - Live Thoughts" cmd /c "chcp 65001 > nul && echo Waiting for Genesis to start... && powershell -Command \"while (-not (Test-Path 'data\genesis_thoughts.log')) { Start-Sleep -Milliseconds 500 }; Get-Content -Wait -Path 'data\genesis_thoughts.log' -Encoding UTF8\""

rem Small pause so the thoughts window appears first
timeout /t 1 /nobreak > nul

rem Start Genesis (passes any extra arguments through)
python src\main.py --live --resume %*
