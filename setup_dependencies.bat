@echo off
title Genesis - Install Dependencies
color 0B

echo.
echo  ==========================================
echo    GENESIS - INSTALL DEPENDENCIES
echo  ==========================================
echo.
echo  This installs the packages Genesis needs
echo  to browse the web and understand language.
echo.
echo  You only need to run this once.
echo.

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found.
    echo  Install Python 3.10+ from https://python.org
    echo  Make sure to tick "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

echo  Step 1 of 3 - Installing packages...
echo  (spacy, trafilatura, ddgs, rich, psutil)
echo.
pip install spacy trafilatura ddgs rich psutil
if errorlevel 1 (
    echo.
    echo  WARNING: Some packages may not have installed cleanly.
    echo  Try running this file as Administrator if errors appear.
    echo.
)

echo.
echo  Step 2 of 3 - Downloading English language model for spaCy...
echo  (about 12 MB, downloads once)
echo.
python -m spacy download en_core_web_sm
if errorlevel 1 (
    echo.
    echo  WARNING: spaCy model download failed.
    echo  Genesis will still work using its built-in extractor.
    echo  Try again later if you have internet issues.
    echo.
)

echo.
echo  Step 3 of 3 - Verifying installs...
echo.
python -c "import spacy; nlp = spacy.load('en_core_web_sm'); print('  spaCy OK -', spacy.__version__)" 2>nul || echo   spaCy: not available (Genesis will use fallback)
python -c "import trafilatura; print('  trafilatura OK -', trafilatura.__version__)" 2>nul || echo   trafilatura: not available
python -c "from ddgs import DDGS; print('  ddgs OK')" 2>nul || python -c "from duckduckgo_search import DDGS; print('  duckduckgo_search OK')" 2>nul || echo   web search: not available

echo.
echo  ==========================================
echo    All done! You can close this window.
echo    Run launch_genesis.bat to start Genesis.
echo  ==========================================
echo.
pause
