<#
.SYNOPSIS
  Start Sift als bureaubladprogramma vanuit deze map (dev-modus van de launcher).

.DESCRIPTION
  Bouwt de launcher (installer\launcher, C#/.NET 8 + WebView2) als dat nodig is en start hem. De launcher merkt dat
  hij in de repo staat (geen python\python.exe naast de exe) en gebruikt dan .venv\Scripts\python.exe met deze map
  als werkmap; er is geen bootstrap. Maak de virtuele omgeving eerst aan met start.ps1 (of handmatig).

  Projecten staan standaard in .\projects (zoals bij start.ps1). Logboek: %LOCALAPPDATA%\Sift\sift.log.

.PARAMETER Port       serverpoort (standaard 8765)
.PARAMETER Projects   projectenmap (standaard .\projects)
.PARAMETER Rebuild    launcher opnieuw bouwen, ook als hij up-to-date lijkt
.PARAMETER DevTools   contextmenu en ontwikkelhulpmiddelen van WebView2 aanzetten
.PARAMETER Browser    geen eigen venster: Sift in de standaardbrowser openen

.EXAMPLE
  .\start-app.ps1
  .\start-app.ps1 -Port 8778 -Projects C:\tmp\sift-test -DevTools
#>
[CmdletBinding()]
param(
    [int]$Port = 8765,
    [string]$Projects,
    [switch]$Rebuild,
    [switch]$DevTools,
    [switch]$Browser,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest
)
$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
$proj = Join-Path $repo "installer\launcher"
$exe = Join-Path $proj "bin\Release\net8.0-windows\win-x64\Sift.exe"

if (-not (Test-Path (Join-Path $repo ".venv\Scripts\python.exe"))) {
    throw "Geen .venv gevonden. Maak die eerst aan met .\start.ps1 (dat installeert ook de afhankelijkheden)."
}
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw "dotnet SDK niet gevonden: winget install Microsoft.DotNet.SDK.8"
}

# Bouwen als de exe ontbreekt of een bronbestand nieuwer is.
$sources = Get-ChildItem $proj -File | Where-Object { $_.Extension -in ".cs", ".csproj", ".manifest" }
$needBuild = $Rebuild -or -not (Test-Path $exe) -or (($sources | Measure-Object LastWriteTime -Maximum).Maximum -gt (Get-Item $exe).LastWriteTime)
if ($needBuild) {
    Write-Host "Launcher bouwen (dotnet build -c Release)..." -ForegroundColor Cyan
    & dotnet build (Join-Path $proj "Sift.csproj") -c Release -nologo -v q
    if ($LASTEXITCODE -ne 0) { throw "dotnet build mislukt" }
}

$launcherArgs = @("--port", $Port)
if ($Projects) {
    New-Item -ItemType Directory -Force $Projects | Out-Null
    $launcherArgs += @("--projects", (Resolve-Path $Projects).Path)
}
if ($DevTools) { $launcherArgs += "--devtools" }
if ($Browser) { $launcherArgs += "--browser" }
if ($Rest) { $launcherArgs += $Rest }
Write-Host "Sift starten: $exe $($launcherArgs -join ' ')" -ForegroundColor Cyan
Start-Process $exe -ArgumentList $launcherArgs
