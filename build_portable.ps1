$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectRoot ".venv-build\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    python -m venv (Join-Path $ProjectRoot ".venv-build")
}

& $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot "requirements-build.txt")

& $VenvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --noconsole `
    --name "BackupReportPortable" `
    --add-data "web;web" `
    --collect-all reportlab `
    (Join-Path $ProjectRoot "app.py")

$OutputRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot "output\portable"))
$ReleaseName = "BackupReportPortable-v0.4.0-history"
$PortableRoot = [IO.Path]::GetFullPath((Join-Path $OutputRoot $ReleaseName))
if (-not $PortableRoot.StartsWith($OutputRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe portable output path: $PortableRoot"
}
if (Test-Path -LiteralPath $PortableRoot) {
    Remove-Item -LiteralPath $PortableRoot -Recurse -Force
}
New-Item -ItemType Directory -Path (Split-Path -Parent $PortableRoot) -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $ProjectRoot "dist\BackupReportPortable") -Destination $PortableRoot -Recurse

$PreviousSettings = Join-Path $OutputRoot "BackupReportPortable-v0.3.0-api\data\settings.json"
if (-not (Test-Path -LiteralPath $PreviousSettings)) {
    $PreviousSettings = Join-Path $OutputRoot "BackupReportPortable-v0.2.0-probe\data\settings.json"
}
if (Test-Path -LiteralPath $PreviousSettings) {
    New-Item -ItemType Directory -Path (Join-Path $PortableRoot "data") -Force | Out-Null
    Copy-Item -LiteralPath $PreviousSettings -Destination (Join-Path $PortableRoot "data\settings.json")
}

$PreviousReports = Join-Path $OutputRoot "BackupReportPortable-v0.3.0-api\reports"
if (Test-Path -LiteralPath $PreviousReports) {
    New-Item -ItemType Directory -Path (Join-Path $PortableRoot "reports") -Force | Out-Null
    Copy-Item -Path (Join-Path $PreviousReports "*.pdf") -Destination (Join-Path $PortableRoot "reports") -ErrorAction SilentlyContinue
}

$ZipPath = Join-Path $OutputRoot ($ReleaseName + ".zip")
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -LiteralPath $PortableRoot -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Output $PortableRoot
Write-Output $ZipPath
