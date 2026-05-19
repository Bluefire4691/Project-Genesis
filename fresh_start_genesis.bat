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

echo.
echo  Clearing Genesis memory...

cd /d "%~dp0project-genesis"

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
echo  Genesis memory cleared. Starting fresh session...
echo  Genesis will think and learn continuously.
echo  Type anything to talk. Use /quit to exit.
echo.

python src/main.py --open-only --live

echo.
echo  Genesis session ended.
pause
