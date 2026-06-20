@echo off
rem Genesis Windows Launcher
rem Single clean window. Genesis thinks silently in the background and
rem only surfaces what it chooses to express, plus a quiet status line.
rem
rem Usage:
rem   launch_genesis.bat                 -- resume + self-directed (default)
rem   launch_genesis.bat --speed 8       -- start faster
rem   launch_genesis.bat --fetch-topics 5
rem
rem Live resource controls (type while it runs):
rem   speed N (1-10)   memory N   fetch N   explore
rem
rem Requirements: Python 3.10+ on PATH, pip install -r requirements.txt

chcp 65001 > nul

rem Install GUI dependencies if missing (one-time)
python -c "import PyQt6" >nul 2>&1 || pip install PyQt6 matplotlib >nul 2>&1

python src\gui.py --resume --self-directed --speed 8 --batch 10 %*
