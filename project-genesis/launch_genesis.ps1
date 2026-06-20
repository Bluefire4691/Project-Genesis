# Genesis Windows Launcher (PowerShell)
# Single clean window. Genesis thinks silently in the background and only
# surfaces what it chooses to express, plus a quiet status line.
#
# Usage:
#   .\launch_genesis.ps1                  -- resume + self-directed (default)
#   .\launch_genesis.ps1 --speed 8        -- start faster
#   .\launch_genesis.ps1 --fetch-topics 5
#
# Live resource controls (type while it runs):
#   speed N (1-10)   memory N   fetch N   explore
#
# Requirements: Python 3.10+ on PATH, pip install -r requirements.txt

# Set UTF-8 for this window
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$host.UI.RawUI.WindowTitle = "Genesis"

$ProjectRoot = $PSScriptRoot

# Install GUI dependencies if missing
python -c "import PyQt6" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing desktop GUI dependencies (PyQt6 + matplotlib)..."
    pip install PyQt6 matplotlib
}

# Launch the desktop GUI
& python (Join-Path $ProjectRoot "src\gui.py") --resume --self-directed --speed 8 --batch 10 @args
