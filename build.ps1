# Build TGDeleter.exe into project root. Run: .\build.ps1
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $root) { $root = Get-Location }
Set-Location $root

$exe = Join-Path $root "TGDeleter.exe"
if (Test-Path $exe) {
    Remove-Item $exe -Force
    Write-Host "Removed old TGDeleter.exe"
}
python build_exe.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (Test-Path $exe) {
    Write-Host "Done: TGDeleter.exe"
} else {
    Write-Host "Error: exe not found. Check dist\TGDeleter.exe"
    exit 1
}
