# publish-msi.ps1 - publish the built NAI OFFICE installer under a stable name.
#
# WHY THIS EXISTS
# Release links must not carry the version. If the website, the README or an
# updater points at "NAI Office_27.2.0.0.alpha0_...msi", every release breaks
# every link. This script publishes:
#
#   <out>/NAIOffice-Windows-x64.msi                     <- canonical, always this URL
#   <out>/archive/NAIOffice-<version>-Windows-x64.msi   <- immutable per release
#   <out>/latest.json                                   <- version, size, sha256, url
#
# Upload the canonical file over the previous one and keep the archive copy.
# Consumers use https://a.nanotrik.ai/naioffice/NAIOffice-Windows-x64.msi, or
# read latest.json to show the version and verify the download.
#
# Usage:
#   pwsh -File writer2027/publish-msi.ps1
#   pwsh -File writer2027/publish-msi.ps1 -SourceMsi <path> -OutDir dist -BaseUrl https://a.nanotrik.ai/naioffice

[CmdletBinding()]
param(
    [string]$SourceMsi,
    [string]$OutDir = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..')).Path 'dist'),
    [string]$BaseUrl = 'https://a.nanotrik.ai/naioffice',
    [string]$CanonicalName = 'NAIOffice-Windows-x64.msi'
)

$ErrorActionPreference = 'Stop'

function Get-NewestInstaller {
    param([string]$Root)
    $candidates = Get-ChildItem -LiteralPath $Root -Recurse -Filter '*.msi' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '[\\/]installation[\\/]' -and $_.Name -notmatch 'languagepack|helppack' } |
        Sort-Object LastWriteTime -Descending
    if (-not $candidates) { throw "No MSI found under $Root. Build the installer first (make instsetoo)." }
    return $candidates[0]
}

function Get-MsiProductVersion {
    param([string]$Path)
    $installer = New-Object -ComObject WindowsInstaller.Installer
    $db = $installer.GetType().InvokeMember('OpenDatabase', 'InvokeMethod', $null, $installer, @($Path, 0))
    $view = $db.GetType().InvokeMember('OpenView', 'InvokeMethod', $null, $db, @("SELECT Value FROM Property WHERE Property='ProductVersion'"))
    $view.GetType().InvokeMember('Execute', 'InvokeMethod', $null, $view, $null) | Out-Null
    $record = $view.GetType().InvokeMember('Fetch', 'InvokeMethod', $null, $view, $null)
    if ($record -eq $null) { return '0.0.0.0' }
    return $record.GetType().InvokeMember('StringData', 'GetProperty', $null, $record, @(1))
}

if (-not $SourceMsi) {
    $SourceMsi = (Get-NewestInstaller -Root (Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..')).Path 'workdir')).FullName
}
if (-not (Test-Path -LiteralPath $SourceMsi)) { throw "MSI not found: $SourceMsi" }

$version = Get-MsiProductVersion -Path $SourceMsi
$archiveName = 'NAIOffice-{0}-Windows-x64.msi' -f $version

$canonicalPath = Join-Path $OutDir $CanonicalName
$archiveDir = Join-Path $OutDir 'archive'
$archivePath = Join-Path $archiveDir $archiveName
$manifestPath = Join-Path $OutDir 'latest.json'

New-Item -ItemType Directory -Force -Path $OutDir, $archiveDir | Out-Null
Copy-Item -LiteralPath $SourceMsi -Destination $canonicalPath -Force
Copy-Item -LiteralPath $SourceMsi -Destination $archivePath -Force

$hash = (Get-FileHash -LiteralPath $canonicalPath -Algorithm SHA256).Hash
$size = (Get-Item -LiteralPath $canonicalPath).Length
$manifest = [ordered]@{
    product      = 'NAI OFFICE'
    version      = $version
    platform     = 'Windows x86-64'
    fileName     = $CanonicalName
    url          = ($BaseUrl.TrimEnd('/') + '/' + $CanonicalName)
    size         = $size
    sha256       = $hash
    publishedUtc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    archive      = ($BaseUrl.TrimEnd('/') + '/archive/' + $archiveName)
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding utf8

Write-Output "source    : $SourceMsi"
Write-Output "canonical : $canonicalPath"
Write-Output "archive   : $archivePath"
Write-Output "manifest  : $manifestPath"
Write-Output ("version   : {0}" -f $version)
Write-Output ("size      : {0:N1} MB" -f ($size / 1MB))
Write-Output ("sha256    : {0}" -f $hash)
Write-Output ("url       : {0}/{1}" -f $BaseUrl.TrimEnd('/'), $CanonicalName)
