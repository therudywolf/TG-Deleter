# Auto-build TGDeleter.exe into the project root.
#   Run:  .\build.ps1
#
# Bootstraps a venv if needed, installs runtime + build dependencies,
# then runs build_exe.py. Safe to re-run; only missing pieces are installed.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = Get-Location }
Set-Location $root

$py = Join-Path $root "venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "[build] Creating virtual environment..."
    python -m venv venv
}

Write-Host "[build] Installing dependencies..."
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -r requirements.txt
& $py -m pip install "pyinstaller>=6.0.0"

$exe = Join-Path $root "TGDeleter.exe"
if (Test-Path $exe) {
    Remove-Item $exe -Force
    Write-Host "[build] Removed old TGDeleter.exe"
}

Write-Host "[build] Building executable..."
& $py build_exe.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (Test-Path $exe) {
    Write-Host "[build] Done: TGDeleter.exe"
} else {
    Write-Host "[build] Error: exe not found. Check dist\TGDeleter.exe"
    exit 1
}
