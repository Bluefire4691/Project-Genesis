@echo off
setlocal enabledelayedexpansion
title Genesis - Set up llama.cpp + model
color 0B

rem ===========================================================================
rem  Downloads llama.cpp (Vulkan build - works on AMD, NVIDIA and Intel),
rem  fetches a Qwen3-8B GGUF, and starts llama-server.
rem
rem  Vulkan first because it needs no ROCm install and works on every vendor.
rem  Once this is running, setup_llamacpp_rocm.bat can be compared against it
rem  for the per-workload benchmark (board 0.2b).
rem ===========================================================================

set "ROOT=%~dp0"
set "LLAMA_DIR=%ROOT%llama"
set "MODEL_DIR=%ROOT%models"

rem Change these two lines if you want a different model.
set "MODEL_FILE=Qwen3-8B-Q4_K_M.gguf"
set "MODEL_URL=https://huggingface.co/unsloth/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf?download=true"

echo.
echo  ==========================================
echo    GENESIS - LLAMA.CPP SETUP
echo  ==========================================
echo.

rem --- 1. llama.cpp -----------------------------------------------------------
if exist "%LLAMA_DIR%\llama-server.exe" (
    echo  [1/3] llama.cpp already present - skipping.
    goto :model
)

echo  [1/3] Fetching the latest llama.cpp Vulkan build for Windows...
mkdir "%LLAMA_DIR%" 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$r = Invoke-RestMethod 'https://api.github.com/repos/ggml-org/llama.cpp/releases/latest' -Headers @{'User-Agent'='genesis'};" ^
  "$a = $r.assets | Where-Object { $_.name -like '*win*vulkan*x64*.zip' } | Select-Object -First 1;" ^
  "if (-not $a) { $a = $r.assets | Where-Object { $_.name -like '*win*vulkan*.zip' } | Select-Object -First 1 };" ^
  "if (-not $a) { Write-Host '  Could not find a Vulkan asset. Open https://github.com/ggml-org/llama.cpp/releases and download the win-vulkan-x64 zip manually into .\llama\'; exit 1 };" ^
  "Write-Host ('  downloading ' + $a.name + ' (' + [math]::Round($a.size/1MB) + ' MB)');" ^
  "Invoke-WebRequest $a.browser_download_url -OutFile '%LLAMA_DIR%\llama.zip';" ^
  "Expand-Archive -Path '%LLAMA_DIR%\llama.zip' -DestinationPath '%LLAMA_DIR%' -Force;" ^
  "Remove-Item '%LLAMA_DIR%\llama.zip';" ^
  "$exe = Get-ChildItem -Path '%LLAMA_DIR%' -Filter 'llama-server.exe' -Recurse | Select-Object -First 1;" ^
  "if ($exe -and $exe.DirectoryName -ne '%LLAMA_DIR%') { Get-ChildItem $exe.DirectoryName | Move-Item -Destination '%LLAMA_DIR%' -Force };" ^
  "Write-Host '  llama.cpp ready.'"

if errorlevel 1 (
    echo.
    echo  ERROR: llama.cpp download failed. See the message above.
    echo.
    pause
    exit /b 1
)

:model
rem --- 2. model ---------------------------------------------------------------
mkdir "%MODEL_DIR%" 2>nul
if exist "%MODEL_DIR%\%MODEL_FILE%" (
    echo  [2/3] Model already present - skipping.
    goto :serve
)

echo.
echo  [2/3] Downloading %MODEL_FILE% ^(about 5 GB - this takes a while^)...
echo        If this 404s, open the URL at the top of this script in a browser,
echo        pick any Q4_K_M .gguf, and save it to .\models\
echo.
curl -L --fail --progress-bar -o "%MODEL_DIR%\%MODEL_FILE%" "%MODEL_URL%"

if errorlevel 1 (
    echo.
    echo  ERROR: model download failed.
    echo  Download a Qwen3-8B Q4_K_M GGUF manually into: %MODEL_DIR%
    echo  Then re-run this script.
    echo.
    pause
    exit /b 1
)

:serve
rem --- 3. serve ---------------------------------------------------------------
echo.
echo  [3/3] Starting llama-server on port 8080.
echo.
echo    Leave THIS WINDOW OPEN. Open a second terminal to run the test.
echo    Verify it works: http://127.0.0.1:8080  in a browser.
echo.
echo  ==========================================
echo.

"%LLAMA_DIR%\llama-server.exe" ^
    -m "%MODEL_DIR%\%MODEL_FILE%" ^
    --host 127.0.0.1 --port 8080 ^
    -c 8192 ^
    -ngl 99 ^
    --jinja

echo.
echo  Server exited.
pause
