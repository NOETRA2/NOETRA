[CmdletBinding()]
param(
    [string]$InstallDirectory = (Join-Path $env:LOCALAPPDATA 'Programs/NOETRA'),
    [switch]$Yes
)
$ErrorActionPreference = 'Stop'
$archiveName = 'noetra-0.1.0-alpha.3.tgz'
$archive = Join-Path $PSScriptRoot $archiveName
$manifestPath = Join-Path $PSScriptRoot 'SHA256SUMS.json'
if (!(Test-Path -LiteralPath $archive -PathType Leaf) -or !(Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw 'Extract the entire NOETRA standalone ZIP first. Its package and checksum file must be beside this installer.'
}
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (!$nodeCommand -or !$npmCommand) {
    throw 'Node.js and npm are required. Install a supported Node.js release from https://nodejs.org/ first. Nothing was installed.'
}
$nodeVersion = (& $nodeCommand.Source --version).TrimStart('v')
if ($LASTEXITCODE -ne 0) { throw 'Cannot check Node.js.' }
$parts = $nodeVersion.Split('.')
$major = [int]$parts[0]
$minor = [int]$parts[1]
if (!(($major -eq 24 -and $minor -ge 11) -or $major -ge 26)) {
    throw "Node.js $nodeVersion is unsupported. Use Node.js 24.11+ (24.x) or 26+."
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$expected = $manifest.$archiveName
$actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if (!$expected -or $actual -ne $expected) { throw 'Package checksum does not match. Nothing was installed.' }
$resolvedInstall = [IO.Path]::GetFullPath($InstallDirectory)
if ($resolvedInstall -eq [IO.Path]::GetPathRoot($resolvedInstall) -or $resolvedInstall -eq [Environment]::GetFolderPath('UserProfile')) {
    throw 'Choose a dedicated NOETRA folder, not a drive or home directory.'
}
if (Test-Path -LiteralPath $resolvedInstall) {
    if ((Get-ChildItem -LiteralPath $resolvedInstall -Force | Measure-Object).Count -gt 0) {
        throw 'The chosen folder is not empty. Select a new dedicated directory; existing installations will not be overwritten.'
    }
}
Write-Host ''
Write-Host 'NOETRA — Universal Cognitive Engine (developer alpha)'
Write-Host "Install directory: $resolvedInstall"
Write-Host 'Installs only NOETRA and its npm runtime libraries. Internet is needed for those libraries.'
Write-Host 'No Nexa apps, REA, AI models, cloud account, PATH changes or client registrations are installed.'
if (!$Yes) {
    $answer = Read-Host 'Type INSTALL to continue'
    if ($answer -cne 'INSTALL') { Write-Host 'Cancelled. Nothing installed.'; return }
}
New-Item -ItemType Directory -Path $resolvedInstall -Force | Out-Null
& $npmCommand.Source install --prefix $resolvedInstall --ignore-scripts --no-audit --no-fund --save-exact $archive
if ($LASTEXITCODE -ne 0) {
    throw "NOETRA installation did not finish. Partial dependency files may remain in $resolvedInstall; no other apps were changed."
}
$launcher = Join-Path $resolvedInstall 'node_modules/.bin/noetra.cmd'
& $launcher --version
if ($LASTEXITCODE -ne 0) { throw 'Package installed but the CLI version check failed.' }
Write-Host ''
Write-Host 'NOETRA installed. It is a command-line/AI-agent tool, not a graphical application.'
Write-Host "Executable: $launcher"
Write-Host 'Run that executable with test to check MCP/SQLite/Z3, or setup to preview host registration.'
