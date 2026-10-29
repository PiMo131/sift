# Start Sift. Maakt bij de eerste keer een virtuele omgeving en installeert de afhankelijkheden.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Virtuele omgeving aanmaken..."
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    $wg = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $wg) { Write-Host "ffmpeg niet gevonden, installeren via winget..."; winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements }
}
.\.venv\Scripts\python.exe -m sift @args
