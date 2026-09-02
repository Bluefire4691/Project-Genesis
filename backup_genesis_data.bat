@echo off
title Genesis - Backup Data (RUN THIS BEFORE ANYTHING ELSE)
color 0E

echo.
echo  ==========================================
echo    GENESIS - BACKUP ACCUMULATED DATA
echo  ==========================================
echo.
echo  Your databases are NOT in git (data/ is gitignored).
echo  They exist only on this machine. The interaction log -
echo  every conversation you have had with Genesis - cannot
echo  be regenerated from anything.
echo.

cd /d "%~dp0project-genesis"

set STAMP=%DATE:~-4%%DATE:~4,2%%DATE:~7,2%_%TIME:~0,2%%TIME:~3,2%
set STAMP=%STAMP: =0%
set DEST=%~dp0backups\genesis_%STAMP%

if not exist "%~dp0backups" mkdir "%~dp0backups"
mkdir "%DEST%" 2>nul

echo  Backing up to: %DEST%
echo.

if exist data\genesis_memory.db (
    copy /Y data\genesis_memory.db "%DEST%\" >nul
    echo   [ok] genesis_memory.db
) else (
    echo   [--] genesis_memory.db not found
)

if exist data\interaction_log.db (
    copy /Y data\interaction_log.db "%DEST%\" >nul
    echo   [ok] interaction_log.db   ^(irreplaceable^)
) else (
    echo   [--] interaction_log.db not found
)

if exist data\reading_positions.json (
    copy /Y data\reading_positions.json "%DEST%\" >nul
    echo   [ok] reading_positions.json
)

if exist data\book_cache (
    xcopy /E /I /Q /Y data\book_cache "%DEST%\book_cache" >nul
    echo   [ok] book_cache
)

echo.
echo  ==========================================
echo    BACKUP COMPLETE
echo  ==========================================
echo.
echo  Location: %DEST%
echo.
echo  STRONGLY RECOMMENDED: copy that folder somewhere
echo  off this machine too - USB drive, cloud drive, anywhere.
echo  Losing it loses the whole history of the project.
echo.
pause
