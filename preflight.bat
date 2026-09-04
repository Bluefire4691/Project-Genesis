@echo off
title Genesis - Preflight Check
color 0E
cd /d "%~dp0"

echo.
echo  ==========================================
echo    GENESIS - PREFLIGHT
echo  ==========================================
echo.
echo  Checks everything the falsification test needs, and tells you
echo  exactly what to fix if something is missing.
echo.

set FAIL=0

rem --- Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo  [X] Python not found. Install 3.11+ from python.org, tick "Add to PATH".
    set FAIL=1
) else (
    for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  [ok] %%v
)

rem --- backup ---
if exist "backups\" (
    echo  [ok] backups\ folder exists
) else (
    echo  [X] NO BACKUP FOUND. Run backup_genesis_data.bat FIRST.
    echo       Your databases are gitignored - they exist only on this machine.
    set FAIL=1
)

rem --- v1 databases ---
if exist "project-genesis\data\genesis_memory.db" (
    echo  [ok] genesis_memory.db present ^(needed for --corpus live^)
) else (
    echo  [!] genesis_memory.db not found - the 'live' corpus will be skipped.
    echo       The designed corpus still runs, but only measures a ceiling.
)

rem --- llama-server reachable ---
powershell -NoProfile -Command ^
  "try { $r = Invoke-RestMethod 'http://127.0.0.1:8080/props' -TimeoutSec 5; " ^
  "  Write-Host ('  [ok] llama-server responding, context = ' + $r.default_generation_settings.n_ctx) } " ^
  "catch { Write-Host '  [X] llama-server NOT reachable on 127.0.0.1:8080'; " ^
  "  Write-Host '       Run setup_llamacpp.bat in another window and leave it open.'; exit 1 }"
if errorlevel 1 set FAIL=1

rem --- does it actually generate? ---
powershell -NoProfile -Command ^
  "try { $b = @{ model='local'; messages=@(@{role='user';content='Reply with the single word: ready'}); max_tokens=8; temperature=0 } | ConvertTo-Json -Depth 5; " ^
  "  $r = Invoke-RestMethod 'http://127.0.0.1:8080/v1/chat/completions' -Method Post -Body $b -ContentType 'application/json' -TimeoutSec 120; " ^
  "  Write-Host ('  [ok] generation works -> ' + $r.choices[0].message.content.Trim()) } " ^
  "catch { Write-Host '  [X] server is up but generation failed:'; Write-Host ('       ' + $_.Exception.Message); exit 1 }" 2>nul
if errorlevel 1 (
    echo       ^(If the model is still loading, wait a minute and re-run.^)
    set FAIL=1
)

echo.
if "%FAIL%"=="1" (
    color 0C
    echo  ==========================================
    echo    NOT READY - fix the [X] items above
    echo  ==========================================
) else (
    color 0A
    echo  ==========================================
    echo    READY. Run this next:
    echo.
    echo      cd project-genesis
    echo      python falsification_test.py --corpus both
    echo  ==========================================
)
echo.
pause
