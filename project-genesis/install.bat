@echo off
echo.
echo  Project Genesis — Install
echo  ========================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found.
    echo  Install Python 3.11+ from https://python.org then re-run this script.
    pause
    exit /b 1
)

echo  [1/4] Installing Python packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo  ERROR: pip install failed.
    pause
    exit /b 1
)

echo.
echo  [2/4] Installing Playwright browser (Chromium ~120 MB)...
python -m playwright install chromium
if errorlevel 1 (
    echo  WARNING: Playwright browser install failed.
    echo  Genesis will fall back to requests-only browsing.
)

echo.
echo  [3/4] Downloading WordNet dictionary (~10 MB, works offline after this)...
python -c "import nltk; nltk.download('wordnet', quiet=True); nltk.download('omw-1.4', quiet=True); print('  WordNet ready.')"

echo.
echo  [4/4] Done.
echo.
echo  To run Genesis:
echo.
echo    Double-click  launch_genesis.bat   (recommended)
echo.
echo  Or from a terminal:
echo    cd src
echo    python ui.py                 <- first run (builds foundation, ~1 min)
echo    python ui.py --resume --self-directed
echo.
echo  Once it's running, type to talk. Live resource controls:
echo    speed N (1-10)   memory N   fetch N   explore
echo.
echo  Optional — LLM voice (richer conversation):
echo    Install Ollama from https://ollama.com
echo    Then: ollama pull llama3.2:3b
echo    Genesis auto-detects it on next run.
echo.
pause
