<#
    Genesis - llama.cpp + model setup.

    Real PowerShell rather than PowerShell-inlined-in-batch: the caret
    continuation and quote escaping in a .bat file is fragile and breaks
    outright on paths containing spaces.

    Vulkan build by default - no ROCm install needed, works on AMD, NVIDIA
    and Intel. ROCm becomes the second arm of the 0.2b benchmark later.

    Usage:
        powershell -ExecutionPolicy Bypass -File setup_llamacpp.ps1
        ... -Backend rocm        # try the HIP/ROCm build instead
        ... -SkipServer          # download only, don't start the server
        ... -ModelUrl "<url>"    # use a different GGUF
#>

[CmdletBinding()]
param(
    [ValidateSet('vulkan', 'rocm', 'cpu')]
    [string]$Backend = 'vulkan',
    [string]$ModelUrl = 'https://huggingface.co/unsloth/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf',
    [string]$ModelFile = 'Qwen3-8B-Q4_K_M.gguf',
    [int]$Port = 8080,
    [int]$Context = 8192,
    [switch]$SkipServer
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is ~10x faster without the progress bar

$Root     = Split-Path -Parent $MyInvocation.MyCommand.Path
$LlamaDir = Join-Path $Root 'llama'
$ModelDir = Join-Path $Root 'models'

function Say([string]$m, [string]$c = 'Gray') { Write-Host "  $m" -ForegroundColor $c }
function Ok ([string]$m) { Say "[ok] $m" 'Green' }
function Bad([string]$m) { Say "[X]  $m" 'Red' }

Write-Host ''
Write-Host '  ==========================================' -ForegroundColor Cyan
Write-Host '    GENESIS - LLAMA.CPP SETUP' -ForegroundColor Cyan
Write-Host '  ==========================================' -ForegroundColor Cyan
Write-Host ''
Say "PowerShell $($PSVersionTable.PSVersion)  |  backend: $Backend"
Say "install dir: $Root"
Write-Host ''

# --------------------------------------------------------------------------
# 1. llama.cpp
# --------------------------------------------------------------------------
$serverExe = Join-Path $LlamaDir 'llama-server.exe'

if (Test-Path $serverExe) {
    Ok 'llama.cpp already present - skipping download.'
}
else {
    Say '[1/3] Looking up the latest llama.cpp release...'
    New-Item -ItemType Directory -Force -Path $LlamaDir | Out-Null

    try {
        $rel = Invoke-RestMethod 'https://api.github.com/repos/ggml-org/llama.cpp/releases/latest' `
                                 -Headers @{ 'User-Agent' = 'genesis-setup' }
    }
    catch {
        Bad "Could not reach the GitHub API: $($_.Exception.Message)"
        Say ''
        Say 'MANUAL FALLBACK:' 'Yellow'
        Say '  1. Open https://github.com/ggml-org/llama.cpp/releases/latest'
        Say "  2. Download the asset named like:  llama-<build>-bin-win-$Backend-x64.zip"
        Say "  3. Extract it so that llama-server.exe sits directly in:"
        Say "     $LlamaDir"
        Say '  4. Re-run this script.'
        exit 1
    }

    # Match the requested backend, then fall back to anything Windows/x64.
    $patterns = switch ($Backend) {
        'vulkan' { @('*win*vulkan*x64*.zip', '*win*vulkan*.zip') }
        'rocm'   { @('*win*hip*x64*.zip', '*win*rocm*x64*.zip', '*win*hip*.zip') }
        'cpu'    { @('*win*cpu*x64*.zip', '*win*avx2*x64*.zip', '*win*x64*.zip') }
    }

    $asset = $null
    foreach ($p in $patterns) {
        $asset = $rel.assets | Where-Object { $_.name -like $p } | Select-Object -First 1
        if ($asset) { break }
    }

    if (-not $asset) {
        Bad "No '$Backend' asset in release $($rel.tag_name)."
        Say 'Available Windows assets:' 'Yellow'
        $rel.assets | Where-Object { $_.name -like '*win*' } |
            ForEach-Object { Say "    $($_.name)" }
        Say ''
        Say "Re-run with a backend that appears above, e.g. -Backend cpu" 'Yellow'
        exit 1
    }

    $zip = Join-Path $LlamaDir 'llama.zip'
    Say "downloading $($asset.name)  ($([math]::Round($asset.size / 1MB)) MB)..."
    Invoke-WebRequest $asset.browser_download_url -OutFile $zip
    Say 'extracting...'
    Expand-Archive -Path $zip -DestinationPath $LlamaDir -Force
    Remove-Item $zip -Force

    # Some releases nest the binaries in a subfolder - flatten it.
    if (-not (Test-Path $serverExe)) {
        $found = Get-ChildItem -Path $LlamaDir -Filter 'llama-server.exe' -Recurse |
                 Select-Object -First 1
        if ($found) {
            Get-ChildItem $found.DirectoryName | Move-Item -Destination $LlamaDir -Force
        }
    }

    if (-not (Test-Path $serverExe)) {
        Bad "Extracted, but llama-server.exe is not in $LlamaDir"
        Say 'Look inside that folder and move the binaries up a level, then re-run.' 'Yellow'
        exit 1
    }
    Ok "llama.cpp ready ($($rel.tag_name))"
}

# --------------------------------------------------------------------------
# 2. model
# --------------------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null
$modelPath = Join-Path $ModelDir $ModelFile

if (Test-Path $modelPath) {
    $gb = [math]::Round((Get-Item $modelPath).Length / 1GB, 2)
    Ok "model already present ($gb GB) - skipping download."
}
else {
    Write-Host ''
    Say "[2/3] Downloading $ModelFile (about 5 GB - this takes a while)..."
    Say 'curl shows a progress bar; leave it running.'
    Write-Host ''

    # curl.exe ships with Windows 10+ and handles the HF redirect and resume
    # far better than Invoke-WebRequest for multi-GB files.
    & curl.exe -L --fail --progress-bar -C - -o $modelPath $ModelUrl

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $modelPath)) {
        Bad 'Model download failed.'
        Say ''
        Say 'MANUAL FALLBACK:' 'Yellow'
        Say '  1. Open this in a browser:'
        Say "     $ModelUrl"
        Say '     (or search HuggingFace for any Qwen3-8B Q4_K_M GGUF)'
        Say "  2. Save it as:  $modelPath"
        Say '  3. Re-run this script - it will skip straight to the server.'
        if (Test-Path $modelPath) { Remove-Item $modelPath -Force }
        exit 1
    }
    Ok 'model downloaded.'
}

# --------------------------------------------------------------------------
# 3. serve
# --------------------------------------------------------------------------
if ($SkipServer) {
    Write-Host ''
    Ok 'Setup complete (server not started, -SkipServer given).'
    exit 0
}

Write-Host ''
Write-Host '  ==========================================' -ForegroundColor Cyan
Write-Host "    STARTING SERVER ON PORT $Port" -ForegroundColor Cyan
Write-Host '  ==========================================' -ForegroundColor Cyan
Write-Host ''
Say 'LEAVE THIS WINDOW OPEN - this is the server.' 'Yellow'
Say 'Open a SECOND terminal to run preflight.bat and the test.'
Say "Check it in a browser: http://127.0.0.1:$Port"
Say 'First start loads ~5 GB into VRAM; give it a minute.'
Write-Host ''

& $serverExe `
    -m $modelPath `
    --host 127.0.0.1 --port $Port `
    -c $Context `
    -ngl 99 `
    --jinja

Write-Host ''
Say "Server exited with code $LASTEXITCODE"
if ($LASTEXITCODE -ne 0) {
    Say 'If this was an out-of-memory or device error, retry with fewer GPU' 'Yellow'
    Say 'layers, e.g.  -ngl 20  (edit this script), or -Backend cpu.' 'Yellow'
}
