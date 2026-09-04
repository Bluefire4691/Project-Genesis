<#
    Genesis - get a local LLM serving, automatically.

    Installs and starts a model server with no manual steps. Tries, in order:

      1. Anything already listening on a known port  -> use it
      2. Ollama already installed                    -> use it
      3. winget install Ollama                       -> silent
      4. Direct OllamaSetup.exe from a stable URL    -> silent

    Ollama rather than llama.cpp because the download URL is STABLE. The
    earlier script matched GitHub release asset names, which change, and it
    broke. Ollama also auto-detects ROCm for AMD cards, so the 9070 XT is
    used without a toolchain install.

    Throughput is not the point here: this exists to run one experiment.
    Backend benchmarking is board item 0.2b and comes afterwards.

    Usage:  powershell -ExecutionPolicy Bypass -File start_llm.ps1
            ... -Model qwen3:14b     # bigger, still fits 16 GB
            ... -NoServe             # install + pull only
#>

[CmdletBinding()]
param(
    [string]$Model = 'qwen3:8b',
    [switch]$NoServe
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

function Say([string]$m, [string]$c = 'Gray') { Write-Host "  $m" -ForegroundColor $c }
function Ok ([string]$m) { Say "[ok] $m" 'Green' }
function Bad([string]$m) { Say "[X]  $m" 'Red' }
function Step([string]$m) { Write-Host ''; Say $m 'Cyan' }

Write-Host ''
Write-Host '  ==========================================' -ForegroundColor Cyan
Write-Host '    GENESIS - LOCAL LLM, AUTOMATIC SETUP' -ForegroundColor Cyan
Write-Host '  ==========================================' -ForegroundColor Cyan

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Ports we know how to talk to, in preference order.
$KnownPorts = @(
    @{ Port = 11434; Name = 'Ollama'    },
    @{ Port = 8080;  Name = 'llama.cpp' },
    @{ Port = 1234;  Name = 'LM Studio' }
)

function Test-Endpoint([int]$Port) {
    try {
        $r = Invoke-RestMethod "http://127.0.0.1:$Port/v1/models" -TimeoutSec 4
        return $true
    } catch { return $false }
}

function Save-Endpoint([int]$Port) {
    $url = "http://127.0.0.1:$Port/v1/chat/completions"
    Set-Content -Path (Join-Path $Root '.llm_endpoint') -Value $url -Encoding ASCII
    [Environment]::SetEnvironmentVariable('GENESIS_LLM_URL', $url, 'User')
    $env:GENESIS_LLM_URL = $url
    Ok "endpoint: $url"
    Say 'written to .llm_endpoint and to your user environment'
    Say '(the test auto-discovers it - no env var needed)'
}

# --------------------------------------------------------------------------
Step '[1/4] Checking for a server already running...'

foreach ($p in $KnownPorts) {
    if (Test-Endpoint $p.Port) {
        Ok "$($p.Name) is already serving on port $($p.Port)"
        Save-Endpoint $p.Port
        Write-Host ''
        Ok 'Nothing to install. Skip to the test.'
        Write-Host ''
        Say 'Next:  cd project-genesis' 'Yellow'
        Say '       python falsification_test.py --corpus both' 'Yellow'
        Write-Host ''
        exit 0
    }
}
Say 'none found - continuing.'

# --------------------------------------------------------------------------
Step '[2/4] Locating or installing Ollama...'

function Find-Ollama {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @(
        "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
        "$env:ProgramFiles\Ollama\ollama.exe",
        "${env:ProgramFiles(x86)}\Ollama\ollama.exe"
    )) { if (Test-Path $p) { return $p } }
    return $null
}

$ollama = Find-Ollama

if ($ollama) {
    Ok "found: $ollama"
}
else {
    # -- try winget (built into Windows 10 21H1+ / 11) ---------------------
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Say 'installing via winget (this opens no windows)...'
        try {
            & winget install --id Ollama.Ollama -e --silent `
                --accept-source-agreements --accept-package-agreements 2>&1 |
                ForEach-Object { if ($_ -match '\S') { Say "    $_" } }
        } catch { Say "    winget path failed: $($_.Exception.Message)" }
        $ollama = Find-Ollama
    }

    # -- fall back to the direct installer (stable URL) --------------------
    if (-not $ollama) {
        Say 'winget unavailable or failed - downloading the installer directly...'
        $setup = Join-Path $env:TEMP 'OllamaSetup.exe'
        try {
            Invoke-WebRequest 'https://ollama.com/download/OllamaSetup.exe' `
                              -OutFile $setup -UseBasicParsing
            Say 'running the installer silently...'
            # Ollama ships an NSIS installer: /S is the silent switch.
            $p = Start-Process -FilePath $setup -ArgumentList '/S' -Wait -PassThru
            Say "installer exited with code $($p.ExitCode)"
            Start-Sleep -Seconds 3
            $ollama = Find-Ollama
        }
        catch {
            Bad "installer download failed: $($_.Exception.Message)"
        }
    }

    if (-not $ollama) {
        Bad 'Could not install Ollama automatically.'
        Say ''
        Say 'This is the one case I cannot script around. Install once from:' 'Yellow'
        Say '  https://ollama.com/download' 'Yellow'
        Say 'then re-run this script - it will detect it and do the rest.' 'Yellow'
        exit 1
    }
    Ok "installed: $ollama"
}

# --------------------------------------------------------------------------
Step '[3/4] Starting the Ollama service...'

# `ollama serve` fails harmlessly if the service is already up.
$serving = $false
foreach ($i in 1..3) {
    if (Test-Endpoint 11434) { $serving = $true; break }
    if ($i -eq 1) {
        Say 'launching background service...'
        Start-Process -FilePath $ollama -ArgumentList 'serve' `
                      -WindowStyle Hidden -ErrorAction SilentlyContinue | Out-Null
    }
    Start-Sleep -Seconds 4
}

if (-not $serving -and -not (Test-Endpoint 11434)) {
    Bad 'Ollama did not come up on port 11434.'
    Say 'Try running  ollama serve  in its own window, then re-run this script.' 'Yellow'
    exit 1
}
Ok 'service is up on port 11434'

# --------------------------------------------------------------------------
Step "[4/4] Ensuring model '$Model' is present..."

$have = $false
try {
    $tags = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10
    $have = [bool]($tags.models | Where-Object { $_.name -eq $Model -or $_.model -eq $Model })
} catch { }

if ($have) {
    Ok "$Model already downloaded"
}
else {
    Say "pulling $Model (about 5 GB - progress below, this takes a while)..."
    Write-Host ''
    & $ollama pull $Model
    if ($LASTEXITCODE -ne 0) {
        Bad "pull failed (exit $LASTEXITCODE)"
        Say "Try a smaller model:  .\start_llm.ps1 -Model qwen3:4b" 'Yellow'
        exit 1
    }
    Ok 'model ready'
}

# --------------------------------------------------------------------------
Write-Host ''
Say 'verifying end to end...' 'Cyan'

try {
    $body = @{
        model    = $Model
        messages = @(@{ role = 'user'; content = 'Reply with the single word: ready' })
        max_tokens = 8
        temperature = 0
    } | ConvertTo-Json -Depth 5

    $r = Invoke-RestMethod 'http://127.0.0.1:11434/v1/chat/completions' `
            -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 240
    Ok "generation works -> $($r.choices[0].message.content.Trim())"
}
catch {
    Bad "the model is installed but generation failed: $($_.Exception.Message)"
    Say 'If it was still loading, wait a minute and re-run this script.' 'Yellow'
    exit 1
}

Save-Endpoint 11434

# Record which model, so the test report can state what produced the numbers.
Set-Content -Path (Join-Path $Root '.llm_model') -Value $Model -Encoding ASCII

Write-Host ''
Write-Host '  ==========================================' -ForegroundColor Green
Write-Host '    READY' -ForegroundColor Green
Write-Host '  ==========================================' -ForegroundColor Green
Write-Host ''
Say 'The service runs in the background - no window to keep open.' 'Green'
Write-Host ''
Say 'Run the experiment:' 'Yellow'
Say '    cd project-genesis' 'Yellow'
Say '    python falsification_test.py --corpus both' 'Yellow'
Say '    python falsification_test.py --corpus live --glossary' 'Yellow'
Write-Host ''
