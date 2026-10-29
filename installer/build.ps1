<#
.SYNOPSIS
  Bouwt de Windows-distributie van Sift: de lichte installer (Inno Setup) en/of de offline-bundels.

.DESCRIPTION
  Zelfde stappen als .github/workflows/release.yml, zodat je lokaal kunt testen zonder CI.

    light         Sift-Setup-<versie>.exe        (Python embed + ffmpeg + sift + launcher + bootstrap)
    offline-cpu   Sift-Offline-CPU-<versie>.zip  (setup-exe + wheels\ met alle cp312/win_amd64-wheels, torch cpu)
    offline-gpu   Sift-Offline-GPU-<versie>.zip.001/.002 (idem, torch cu126 + cuBLAS/cuDNN; gesplitst met 7-Zip)
    all           alle drie

  Vereist: dotnet 8 SDK, Inno Setup 6 (ISCC.exe), Python 3.x met pip (voor de offline-bundels en het icoon),
  7-Zip (alleen offline-bundels). Downloads worden gecachet in installer\.build\dl en op sha256 gecontroleerd.

.PARAMETER Variant   light (standaard) | offline-cpu | offline-gpu | all
.PARAMETER DryRun    Alleen controleren en laten zien wat er zou gebeuren; niets downloaden of bouwen.
.PARAMETER SkipInstaller  Geen nieuwe setup-exe bouwen; de bestaande in dist\ gebruiken (voor offline-bundels in CI).
.PARAMETER OutDir    Uitvoermap (standaard installer\dist).

.EXAMPLE
  .\installer\build.ps1                         # lichte installer
  .\installer\build.ps1 -Variant offline-cpu    # ook de offline-CPU-bundel (ca. 1 GB download)
  .\installer\build.ps1 -Variant all -DryRun
#>
[CmdletBinding()]
param(
    [ValidateSet("light", "offline-cpu", "offline-gpu", "all")]
    [string]$Variant = "light",
    [switch]$DryRun,
    [switch]$SkipInstaller,
    [string]$OutDir
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest is anders tergend traag

# ---------------------------------------------------------------- vaste versies en hashes
$PythonVersion = "3.12.10"                 # laatste 3.12 met Windows-binaries (3.12 is security-only sinds okt 2024)
$PythonUrl     = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$PythonSha256  = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"   # python.org publiceert geen sha256-bestand; hash van de download vastgelegd op 2026-10-30

$FfmpegVersion = "9.0.2"                   # gyan.dev "essentials" build; sha256 van https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip.sha256
$FfmpegUrl     = "https://github.com/GyanD/codexffmpeg/releases/download/$FfmpegVersion/ffmpeg-$FfmpegVersion-essentials_build.zip"
$FfmpegSha256  = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"

$PipVersion    = "26.2.2"
$PipUrl        = "https://files.pythonhosted.org/packages/py3/p/pip/pip-$PipVersion-py3-none-any.whl"
$PipSha256     = "fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"

# torch-variant moet gelijk zijn aan TORCH_VERSION / TORCH_INDEX in payload\bootstrap.py
$TorchVersion  = "2.7.1"
$TorchIndex    = @{ cpu = "https://download.pytorch.org/whl/cpu"; gpu = "https://download.pytorch.org/whl/cu126" }
$TorchSuffix   = @{ cpu = "+cpu"; gpu = "+cu126" }
$CudaPip       = @("nvidia-cublas-cu12", "nvidia-cudnn-cu12")
$SplitSizeMB   = 1900                      # GitHub-release-assets mogen maximaal 2 GiB zijn

# ---------------------------------------------------------------- paden
$Installer = $PSScriptRoot
$Repo      = Split-Path $Installer -Parent
$Build     = Join-Path $Installer ".build"
$Dl        = Join-Path $Build "dl"
$Stage     = Join-Path $Build "stage"
if (-not $OutDir) { $OutDir = Join-Path $Installer "dist" }
$Version   = (Select-String -Path (Join-Path $Repo "sift\__init__.py") -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
if (-not $Version) { throw "Kon __version__ niet lezen uit sift\__init__.py" }
$SetupExe  = Join-Path $OutDir "Sift-Setup-$Version.exe"

$variants = if ($Variant -eq "all") { @("light", "offline-cpu", "offline-gpu") } else { @($Variant) }
$needSetup = -not $SkipInstaller

function Say($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

function Find-Tool([string[]]$candidates, [string]$name) {
    foreach ($c in $candidates) { if ($c -and (Test-Path $c)) { return (Resolve-Path $c).Path } }
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$Iscc = Find-Tool @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe") "ISCC.exe"
$SevenZip = Find-Tool @("$env:ProgramFiles\7-Zip\7z.exe", "${env:ProgramFiles(x86)}\7-Zip\7z.exe", "C:\ProgramData\chocolatey\bin\7z.exe") "7z.exe"
$Dotnet = (Get-Command dotnet -ErrorAction SilentlyContinue).Source
# host-Python (alleen voor pip download en het icoon): "py -3.12" heeft de voorkeur, anders wat er is
$HostPython = $null; $HostPyExe = $null; $HostPyArgs = @()
foreach ($cand in @(@("py", "-3.12"), @("py", "-3"), @("python"), @("python3"))) {
    $exe = $cand[0]; $extra = @($cand | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $v = & $exe @extra -c "import sys; print(sys.version_info >= (3, 9))" 2>$null
    if ($v -eq "True") { $HostPython = ($cand -join " "); $HostPyExe = $exe; $HostPyArgs = $extra; break }
}
function Invoke-HostPython { & $HostPyExe @HostPyArgs @args; return $LASTEXITCODE }

Say "Sift $Version   variant(en): $($variants -join ', ')$(if ($DryRun) { '   [DRY RUN]' })"
Write-Host "    repo:      $Repo"
Write-Host "    uitvoer:   $OutDir"
Write-Host "    ISCC:      $(if ($Iscc) { $Iscc } else { 'NIET GEVONDEN' })"
Write-Host "    dotnet:    $(if ($Dotnet) { $Dotnet } else { 'NIET GEVONDEN' })"
Write-Host "    7-Zip:     $(if ($SevenZip) { $SevenZip } else { 'niet gevonden (alleen nodig voor offline-bundels)' })"
Write-Host "    python:    $(if ($HostPython) { $HostPython } else { 'niet gevonden (nodig voor offline-bundels en icoon)' })"

$needOffline = ($variants | Where-Object { $_ -like "offline-*" }).Count -gt 0
$problems = @()
if ($needSetup -and -not $Iscc)   { $problems += "Inno Setup 6 (ISCC.exe) niet gevonden: winget install JRSoftware.InnoSetup" }
if ($needSetup -and -not $Dotnet) { $problems += "dotnet SDK niet gevonden: winget install Microsoft.DotNet.SDK.8" }
if ($needOffline -and -not $HostPython) { $problems += "Python 3 met pip niet gevonden (nodig voor pip download)" }
if ($needOffline -and -not $SevenZip)   { $problems += "7-Zip niet gevonden (nodig om de bundels te zippen/splitsen): winget install 7zip.7zip" }
if ($SkipInstaller -and -not (Test-Path $SetupExe)) { $problems += "-SkipInstaller maar $SetupExe bestaat niet" }
if ($problems) {
    $problems | ForEach-Object { Write-Host "    FOUT: $_" -ForegroundColor Red }
    if (-not $DryRun) { throw "Ontbrekende hulpmiddelen" }
}

if ($DryRun) {
    Say "Dry run: zou downloaden (met sha256-controle):"
    Write-Host "    $PythonUrl"
    Write-Host "    $FfmpegUrl"
    Write-Host "    $PipUrl"
    if ($needSetup) {
        Say "Dry run: zou bouwen: launcher (dotnet publish), stage, $SetupExe"
    }
    foreach ($v in ($variants | Where-Object { $_ -like "offline-*" })) {
        $kind = $v.Substring(8)
        Say "Dry run: zou pip download doen voor $kind (torch==$TorchVersion$($TorchSuffix[$kind]) via $($TorchIndex[$kind]), cp312/win_amd64) en zippen als Sift-Offline-$($kind.ToUpper())-$Version.zip"
    }
    # syntaxcontrole van de losse onderdelen
    if ($HostPython) {
        if ((Invoke-HostPython -m py_compile (Join-Path $Installer "payload\bootstrap.py") (Join-Path $Installer "make_icon.py")) -ne 0) { throw "bootstrap.py/make_icon.py compileert niet" }
        Write-Host "    bootstrap.py en make_icon.py: syntax ok"
    }
    if ($Dotnet) {
        & $Dotnet build (Join-Path $Installer "launcher\Sift.csproj") -c Release -nologo -v q -o (Join-Path $Build "launcher-dryrun") | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "launcher compileert niet" }
        Write-Host "    launcher: compileert"
    }
    return
}

New-Item -ItemType Directory -Force $Build, $Dl, $OutDir | Out-Null

# ---------------------------------------------------------------- downloads
function Get-Verified([string]$Url, [string]$Sha256, [string]$Dest) {
    if (Test-Path $Dest) {
        $h = (Get-FileHash $Dest -Algorithm SHA256).Hash.ToLower()
        if ($h -eq $Sha256) { Write-Host "    (cache) $(Split-Path $Dest -Leaf)"; return }
        Remove-Item $Dest
    }
    Say "download $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
    $h = (Get-FileHash $Dest -Algorithm SHA256).Hash.ToLower()
    if ($h -ne $Sha256) { Remove-Item $Dest; throw "sha256 klopt niet voor $Url`n  verwacht $Sha256`n  gekregen $h" }
    Write-Host "    sha256 ok"
}

$PythonZip = Join-Path $Dl "python-$PythonVersion-embed-amd64.zip"
$FfmpegZip = Join-Path $Dl "ffmpeg-$FfmpegVersion-essentials_build.zip"
$PipWhl    = Join-Path $Dl "pip-$PipVersion-py3-none-any.whl"

if ($needSetup) {
    Get-Verified $PythonUrl $PythonSha256 $PythonZip
    Get-Verified $FfmpegUrl $FfmpegSha256 $FfmpegZip
    Get-Verified $PipUrl $PipSha256 $PipWhl

    # ------------------------------------------------------------ icoon (uit sift/static/logo.svg)
    $Ico = Join-Path $Installer "sift.ico"
    if (-not (Test-Path $Ico)) {
        if (-not $HostPython) { throw "sift.ico ontbreekt en er is geen Python om het te maken" }
        Say "icoon maken uit sift\static\logo.svg"
        $venv = Join-Path $Build "icotools"
        if (-not (Test-Path "$venv\Scripts\python.exe")) { Invoke-HostPython -m venv $venv | Out-Null }
        & "$venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check pillow resvg-py
        & "$venv\Scripts\python.exe" (Join-Path $Installer "make_icon.py") (Join-Path $Repo "sift\static\logo.svg") $Ico
        if ($LASTEXITCODE -ne 0) { throw "icoon maken mislukt" }
    }

    # ------------------------------------------------------------ launcher
    Say "launcher bouwen (dotnet publish, self-contained single-file)"
    $LauncherOut = Join-Path $Build "launcher"
    & $Dotnet publish (Join-Path $Installer "launcher\Sift.csproj") -c Release -nologo -v q -o $LauncherOut "-p:SiftVersion=$Version"
    if ($LASTEXITCODE -ne 0) { throw "dotnet publish mislukt" }
    $LauncherExe = Join-Path $LauncherOut "Sift.exe"
    if (-not (Test-Path $LauncherExe)) { throw "Sift.exe niet gevonden na publish" }

    # ------------------------------------------------------------ stage
    Say "stage opbouwen in $Stage"
    if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
    New-Item -ItemType Directory -Force "$Stage\app", "$Stage\python", "$Stage\ffmpeg", "$Stage\tools" | Out-Null

    Copy-Item $LauncherExe "$Stage\Sift.exe"

    # sift-pakket zonder caches
    robocopy (Join-Path $Repo "sift") "$Stage\app\sift" /E /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy sift mislukt ($LASTEXITCODE)" }
    Copy-Item (Join-Path $Repo "requirements.txt") "$Stage\app\requirements.txt"
    Copy-Item (Join-Path $Installer "payload\bootstrap.py") "$Stage\app\bootstrap.py"
    Set-Content -Path "$Stage\app\VERSION" -Value $Version -NoNewline -Encoding ascii

    # Python embeddable; ._pth zo aanpassen dat site (en dus pip en Lib\site-packages) werkt en ..\app importeerbaar is
    Expand-Archive $PythonZip -DestinationPath "$Stage\python" -Force
    $pth = Get-ChildItem "$Stage\python\python*._pth" | Select-Object -First 1
    if (-not $pth) { throw "python3xx._pth niet gevonden in de embeddable zip" }
    $zipName = (Get-ChildItem "$Stage\python\python3*.zip" | Select-Object -First 1).Name
    @($zipName, ".", "..\app", "import site") | Set-Content -Path $pth.FullName -Encoding ascii
    Write-Host "    $($pth.Name): $((Get-Content $pth.FullName) -join ' | ')"

    # ffmpeg + ffprobe + licentie
    $ffTmp = Join-Path $Build "ffmpeg-extract"
    if (Test-Path $ffTmp) { Remove-Item $ffTmp -Recurse -Force }
    Expand-Archive $FfmpegZip -DestinationPath $ffTmp -Force
    $ffBin = Get-ChildItem $ffTmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1
    Copy-Item $ffBin.FullName "$Stage\ffmpeg\ffmpeg.exe"
    Copy-Item (Join-Path $ffBin.DirectoryName "ffprobe.exe") "$Stage\ffmpeg\ffprobe.exe"
    $ffRoot = Split-Path $ffBin.DirectoryName -Parent
    foreach ($f in @("LICENSE", "README.txt")) { if (Test-Path "$ffRoot\$f") { Copy-Item "$ffRoot\$f" "$Stage\ffmpeg\$f" } }

    Copy-Item $PipWhl "$Stage\tools\"

    $stageMB = [math]::Round((Get-ChildItem $Stage -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
    Write-Host "    stage: $stageMB MB"

    # ------------------------------------------------------------ Inno Setup
    Say "installer compileren (ISCC)"
    & $Iscc /Q "/DAppVersion=$Version" "/DStageDir=$Stage" "/DOutputDir=$OutDir" (Join-Path $Installer "Sift.iss")
    if ($LASTEXITCODE -ne 0) { throw "ISCC mislukt ($LASTEXITCODE)" }
    $setupMB = [math]::Round((Get-Item $SetupExe).Length / 1MB, 1)
    Say "klaar: $SetupExe ($setupMB MB)"
}

# ---------------------------------------------------------------- offline-bundels
foreach ($v in ($variants | Where-Object { $_ -like "offline-*" })) {
    $kind = $v.Substring(8)                      # cpu | gpu
    $KIND = $kind.ToUpper()
    Say "offline-bundel ${KIND}: wheels downloaden (cp312, win_amd64)"
    $bundle = Join-Path $Build "offline-$kind"
    if (Test-Path $bundle) { Remove-Item $bundle -Recurse -Force }
    $wheels = Join-Path $bundle "wheels"
    New-Item -ItemType Directory -Force $wheels | Out-Null

    # requirements zonder torch/torchaudio/nvidia-* (zelfde filter als bootstrap.py) + constraints die torch vastpinnen
    $req = Get-Content (Join-Path $Repo "requirements.txt") | Where-Object {
        $s = $_.Trim().ToLower()
        $s -and -not $s.StartsWith("#") -and -not ($s -match '^(torch|torchaudio)\b') -and -not $s.StartsWith("nvidia-")
    }
    $reqFile = Join-Path $bundle "requirements-rest.txt"
    $conFile = Join-Path $bundle "constraints.txt"
    $req | Set-Content $reqFile -Encoding ascii
    @("torch==$TorchVersion$($TorchSuffix[$kind])", "torchaudio==$TorchVersion$($TorchSuffix[$kind])") | Set-Content $conFile -Encoding ascii

    $pipArgs = @("-m", "pip", "download", "--disable-pip-version-check", "-d", $wheels,
                 "--platform", "win_amd64", "--python-version", "3.12", "--implementation", "cp", "--abi", "cp312",
                 "--only-binary=:all:", "--extra-index-url", $TorchIndex[$kind],
                 "-c", $conFile, "-r", $reqFile, "torch==$TorchVersion$($TorchSuffix[$kind])", "torchaudio==$TorchVersion$($TorchSuffix[$kind])")
    if ($kind -eq "gpu") { $pipArgs += $CudaPip }
    if ((Invoke-HostPython @pipArgs) -ne 0) { throw "pip download ($kind) mislukt" }
    Set-Content -Path "$wheels\VARIANT" -Value $kind -NoNewline -Encoding ascii
    $n = (Get-ChildItem $wheels -Filter *.whl).Count
    $wheelsMB = [math]::Round((Get-ChildItem $wheels -File | Measure-Object Length -Sum).Sum / 1MB, 0)
    Write-Host "    $n wheels, $wheelsMB MB"
    Remove-Item $reqFile, $conFile

    Copy-Item $SetupExe $bundle
    Copy-Item (Join-Path $Installer "payload\LEESMIJ-offline.txt") (Join-Path $bundle "LEESMIJ.txt")

    $zipBase = Join-Path $OutDir "Sift-Offline-$KIND-$Version.zip"
    Get-ChildItem $OutDir -Filter "Sift-Offline-$KIND-$Version.zip*" | Remove-Item -Force
    $totalMB = $wheelsMB + (Get-Item $SetupExe).Length / 1MB
    # wheels zijn al gecomprimeerd: -mx=1. Boven de limiet van GitHub (2 GiB per asset) splitsen in .zip.001/.002/...
    $zipArgs = @("a", "-tzip", "-mx=1", "-bso0", "-bsp0", $zipBase, "$bundle\*")
    if ($totalMB -gt $SplitSizeMB) { $zipArgs += "-v${SplitSizeMB}m" }
    Say "zippen -> $zipBase$(if ($totalMB -gt $SplitSizeMB) { ' (gesplitst in delen van ' + $SplitSizeMB + ' MB)' })"
    & $SevenZip @zipArgs
    if ($LASTEXITCODE -ne 0) { throw "7-Zip mislukt ($LASTEXITCODE)" }
    Get-ChildItem $OutDir -Filter "Sift-Offline-$KIND-$Version.zip*" | ForEach-Object {
        Write-Host ("    {0}  {1:N0} MB" -f $_.Name, ($_.Length / 1MB))
    }
    Remove-Item $bundle -Recurse -Force
}

Say "gereed"
Get-ChildItem $OutDir | ForEach-Object { Write-Host ("    {0,-45} {1,10:N1} MB" -f $_.Name, ($_.Length / 1MB)) }
