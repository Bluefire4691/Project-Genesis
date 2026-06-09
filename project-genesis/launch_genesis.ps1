# Genesis Windows Launcher (PowerShell)
# Opens two windows: live thoughts (read-only) + conversation.
#
# Usage:
#   .\launch_genesis.ps1                  -- resume last session (default)
#   .\launch_genesis.ps1 --open-only      -- skip curriculum
#   .\launch_genesis.ps1 --cycles 200     -- more cycles before live mode
#
# Requirements: Python 3.9+ on PATH, pip install -r requirements.txt

# Set UTF-8 for this window
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$host.UI.RawUI.WindowTitle = "Genesis - Conversation"

$ProjectRoot = $PSScriptRoot
$ThoughtLog  = Join-Path $ProjectRoot "data\genesis_thoughts.log"

# Ensure data dir exists
if (-not (Test-Path (Split-Path $ThoughtLog))) {
    New-Item -ItemType Directory -Path (Split-Path $ThoughtLog) | Out-Null
}

# Open the live-thoughts window
$ThoughtScript = @"
`$host.UI.RawUI.WindowTitle = 'Genesis - Live Thoughts'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(`$false)
Write-Host 'Waiting for Genesis to start...'
while (-not (Test-Path '$ThoughtLog')) { Start-Sleep -Milliseconds 500 }
Write-Host ''
Get-Content -Wait -Path '$ThoughtLog' -Encoding UTF8
"@

Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $ThoughtScript

# Small pause so the thoughts window appears first
Start-Sleep -Milliseconds 800

# Start Genesis with all passed arguments
& python (Join-Path $ProjectRoot "src\main.py") --live --resume @args
