<#
.SYNOPSIS
  Bouwt de Sift Android-app: dotnet publish -> android\dist\Sift-<versie>.apk

.DESCRIPTION
  Versie komt uit sift\__init__.py (__version__). Met android\Signing.props (zie Signing.props.example)
  wordt de APK met je eigen keystore gesigneerd, anders met de debug-key (prima om zelf te installeren).

.EXAMPLE
  .\android\build.ps1
  .\android\build.ps1 -Configuration Debug
  .\android\build.ps1 -Install        # daarna meteen via adb installeren op het aangesloten toestel
#>
param(
    [string]$Configuration = "Release",
    [switch]$Install
)
$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$repo = Split-Path $root -Parent
$proj = Join-Path $root "Sift.csproj"
$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force $dist | Out-Null

# Version from sift/__init__.py: __version__ = "0.1.0"
$init = Get-Content (Join-Path $repo "sift\__init__.py") -Raw
if ($init -notmatch '__version__\s*=\s*"([^"]+)"') { throw "__version__ not found in sift/__init__.py" }
$version = $Matches[1]
$parts = ($version -replace '[^0-9.].*$', '').Split('.') + @('0', '0', '0')
$versionCode = [int]$parts[0] * 10000 + [int]$parts[1] * 100 + [int]$parts[2]
if ($versionCode -lt 1) { $versionCode = 1 }

$jdk = Get-ChildItem "C:\Program Files\Microsoft\jdk-17*" -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
$sdk = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } elseif ($env:ANDROID_SDK_ROOT) { $env:ANDROID_SDK_ROOT } else { Join-Path $env:LOCALAPPDATA "Android\Sdk" }
$extra = @()
if ($jdk) { $extra += "-p:JavaSdkDirectory=$($jdk.FullName)" }
if (Test-Path $sdk) { $extra += "-p:AndroidSdkDirectory=$sdk" }

$signed = Test-Path (Join-Path $root "Signing.props")
Write-Host "== Sift $version (versionCode $versionCode), $Configuration, $(if ($signed) { 'keystore uit Signing.props' } else { 'debug-signing' }) ==" -ForegroundColor Cyan

dotnet publish $proj -f net8.0-android -c $Configuration `
    "-p:ApplicationDisplayVersion=$version" "-p:ApplicationVersion=$versionCode" @extra
if ($LASTEXITCODE) { throw "dotnet publish (android) failed" }

$publish = Join-Path $root "bin\$Configuration\net8.0-android\publish"
$apk = Get-ChildItem $publish -Filter "*-Signed.apk" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $apk) { throw "signed APK not found in $publish" }
$out = Join-Path $dist "Sift-$version.apk"
Copy-Item $apk.FullName $out -Force

Write-Host "`nAPK: $out ($([math]::Round((Get-Item $out).Length/1MB,1)) MB)" -ForegroundColor Green

if ($Install) {
    $adb = Join-Path $sdk "platform-tools\adb.exe"
    if (-not (Test-Path $adb)) { throw "adb not found: $adb" }
    & $adb install -r $out
}
