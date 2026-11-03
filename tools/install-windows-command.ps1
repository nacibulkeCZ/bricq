[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$bin = Join-Path $env:LOCALAPPDATA 'BRICQ\bin'
New-Item -ItemType Directory -Force -Path $bin | Out-Null
foreach ($file in @('bricq.cmd','bricq-cli.ps1','bricq-push.ps1','WindowsWifi.cs','connect-usb-wifi.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination (Join-Path $bin $file)
}
$repoRoot = (Get-Item $PSScriptRoot).Parent.FullName
Set-Content -LiteralPath (Join-Path (Split-Path -Parent $bin) 'repo-root.txt') -Value $repoRoot -Encoding ASCII
$userPath = [Environment]::GetEnvironmentVariable('Path','User')
$entries = @($userPath -split ';' | Where-Object { $_ })
if ($entries -notcontains $bin) {
    [Environment]::SetEnvironmentVariable('Path', (($entries + $bin) -join ';'), 'User')
}
if (($env:Path -split ';') -notcontains $bin) { $env:Path += ';' + $bin }
Write-Host 'Installed: bricq wifi | bricq wifi off | bricq status | bricq login | bricq push'
Write-Host 'Available in this PowerShell now. Restart other terminal applications to refresh their PATH.'
