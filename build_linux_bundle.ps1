$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutputRoot = Join-Path $ProjectRoot "output\linux"
$BundleName = "PylonBackupReport-v0.8.1-linux"
$Stage = Join-Path $OutputRoot $BundleName
$AppStage = Join-Path $Stage "app"

if (Test-Path -LiteralPath $Stage) {
    Remove-Item -LiteralPath $Stage -Recurse -Force
}
New-Item -ItemType Directory -Path $AppStage -Force | Out-Null

foreach ($File in @("app.py", "api_collector.py", "auth_store.py", "build_backup_report.py", "credential_store.py", "sangfor_capture.py", "synology_api.py")) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot $File) -Destination $AppStage
}
Copy-Item -LiteralPath (Join-Path $ProjectRoot "web") -Destination $AppStage -Recurse
Copy-Item -Path (Join-Path $ProjectRoot "deploy\linux\*") -Destination $Stage -Recurse

$ZipPath = Join-Path $OutputRoot ($BundleName + ".zip")
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -LiteralPath $Stage -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Output $Stage
Write-Output $ZipPath
