# Clip AI local backend starter for Windows PowerShell
# Creates an isolated CPU-only Python environment and starts the API.
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VenvPath = Join-Path $RepoRoot ".venv-clip-ai"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"

Write-Host "=== Clip AI local backend setup ===" -ForegroundColor Cyan
Write-Host "Project folder: $RepoRoot"

# Prefer Python 3.11, then 3.12. Keep existing Python installations untouched.
# Temporarily allow launcher probes to fail so missing versions can fall back cleanly.
$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$PythonSelector = $null
& py -3.11 --version *> $null
if ($LASTEXITCODE -eq 0) { $PythonSelector = "-3.11" }
if (-not $PythonSelector) {
    & py -3.12 --version *> $null
    if ($LASTEXITCODE -eq 0) { $PythonSelector = "-3.12" }
}
$ErrorActionPreference = $PreviousErrorAction
if (-not $PythonSelector) {
    Write-Host "Python 3.11 or 3.12 is required. Install one, then rerun this script." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "[1/5] Creating isolated Python environment..." -ForegroundColor Cyan
    & py $PythonSelector -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
} else {
    Write-Host "[1/5] Reusing existing Clip AI virtual environment." -ForegroundColor Green
}

Write-Host "[2/5] Updating pip tools..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }

Write-Host "[3/5] Installing CPU-only PyTorch and matching audio package..." -ForegroundColor Cyan
& $VenvPython -m pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.10.0" "torchaudio==2.10.0"
if ($LASTEXITCODE -ne 0) { throw "PyTorch installation failed." }

Write-Host "[4/5] Installing FunClip and API dependencies (this may take a while)..." -ForegroundColor Cyan
Push-Location $RepoRoot
try {
    & $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "FunClip dependencies installation failed." }
    & $VenvPython -m pip install -r (Join-Path $RepoRoot "backend\requirements-api.txt")
    if ($LASTEXITCODE -ne 0) { throw "API dependencies installation failed." }
    & $VenvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw "Dependency check failed. Review the output above." }
} finally {
    Pop-Location
}

Write-Host "[5/5] Checking FFmpeg..." -ForegroundColor Cyan
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "FFmpeg was not found. Install FFmpeg and ensure ffmpeg.exe is on PATH." -ForegroundColor Yellow
    Write-Host "Suggested command: winget install Gyan.FFmpeg.Shared"
    exit 1
}
& ffmpeg -version | Select-Object -First 1

# Keep the first-run model smaller than Fun-ASR-Nano; it is more appropriate for a
# modest Windows laptop. Users can override these environment variables if desired.
$env:CLIP_AI_ASR_MODEL = "paraformer"
$env:CLIP_AI_LANG = "en"
$env:PYTHONPATH = "$RepoRoot\funclip;$RepoRoot"
Write-Host "Starting Clip AI API at http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Health check: http://127.0.0.1:8000/api/health"
Write-Host "Leave this PowerShell window open while using Clip AI. Press Ctrl+C to stop."
& $VenvPython -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
