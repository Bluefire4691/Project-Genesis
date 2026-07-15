@echo off
title Project Genesis — Fresh Start
color 0C

echo.
echo  ==========================================
echo    PROJECT GENESIS — FRESH START
echo  ==========================================
echo.
echo  WARNING: This will erase all of Genesis's memories,
echo  relations, and learned knowledge. It cannot be undone.
echo.
set /p CONFIRM="  Type YES to confirm fresh start: "
if /i not "%CONFIRM%"=="YES" (
    echo.
    echo  Cancelled. Genesis memory preserved.
    echo.
    pause
    exit /b 0
)

cd /d "%~dp0project-genesis"

:: Verify GUI dependencies BEFORE touching the memory DB — never wipe
:: Genesis's mind and then fail to start.
python -c "import PyQt6, matplotlib" >nul 2>&1 || (
    echo  Installing desktop GUI dependencies ^(PyQt6 + matplotlib^)...
    pip install PyQt6 matplotlib
)
python -c "import PyQt6, matplotlib" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: could not install PyQt6/matplotlib. Nothing was deleted.
    echo  Run: pip install PyQt6 matplotlib   and try again.
    echo.
    pause
    exit /b 1
)

echo.
echo  Clearing Genesis memory...

:: Remove the database files
if exist data\genesis_memory.db (
    del data\genesis_memory.db
    echo  - Memory database cleared.
)
if exist data\interaction_log.db (
    del data\interaction_log.db
    echo  - Interaction log cleared.
)

:: Remove reading position tracker (Genesis starts books from the beginning)
if exist data\reading_positions.json (
    del data\reading_positions.json
    echo  - Reading positions cleared.
)

:: Remove cached book files (optional — keeps downloads to save bandwidth)
:: Uncomment the next two lines to also clear downloaded books:
:: if exist data\book_cache (
::     rmdir /s /q data\book_cache
::     echo  - Book cache cleared.
:: )

echo.
echo  Genesis memory cleared. Building a new mind from scratch...
echo  (The foundation pass takes about a minute the first time.)
echo.
echo  One clean window. Genesis thinks silently in the background and
echo  only surfaces what it chooses to express. Just type to talk.
echo  Live controls: speed N (1-10)  memory N  fetch N  explore  quit
echo.

chcp 65001 > nul
python src\gui.py --self-directed

echo.
echo  Genesis session ended.
pause
