[CmdletBinding()]
param(
    [string]$UsbAddress = '10.12.194.1',
    [string]$AdminUser = 'stepanek',
    [string]$ProjectPath
)
$ErrorActionPreference = 'Stop'
if ($UsbAddress -notmatch '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' -or $AdminUser -notmatch '^[a-z_][a-z0-9_-]*$') {
    throw 'Invalid USB address or administrator username.'
}
$sourceRoot = Split-Path $PSScriptRoot -Parent
$files = @('tools/install-usb-wifi.ps1', 'tools/connect-usb-wifi.ps1',
    'tools/WindowsWifi.cs', 'tools/bricq-cli.ps1', 'tools/bricq.cmd', 'tools/install-windows-command.ps1',
    'firmware/usb-wifi.py', 'firmware/bricq', 'firmware/bricq-wifi', 'firmware/install-usb-wifi.sh', 'docs/usb-wifi.md', 'docs/requirements.md')
$previousVersions = @{
    'firmware/bricq' = '36DBA52750D33126A55772A20F4B7EADE0470FA4F412BA82780A1342B635841F'
    'firmware/install-usb-wifi.sh' = '932CD369ADEC9F344E33C60675CF25FCC52D77BE1B83F8AB46E50426026684CB'
    'tools/install-usb-wifi.ps1' = '84F34C95273990525992EE78BE2664FB82B6F18853399E91EB17F5E14904AE24'
    'firmware/usb-wifi.py' = 'B8FB1F78EC86AF7EC28A360E3A6CD06DCDCB053A560EC78B25348E8A8D1E345D'
    'docs/usb-wifi.md' = '7D6DFF9EC95848B6227D9E9E7DDF5512BED50CDEE08481B16DC0BFB0087272D8'
}
if ($ProjectPath) {
    $destinationRoot = (Resolve-Path -LiteralPath $ProjectPath).Path
    if (-not (Test-Path -LiteralPath (Join-Path $destinationRoot '.git'))) { throw 'ProjectPath must be the existing Git repository.' }
    # Check every destination before copying anything; preserve user edits.
    foreach ($file in $files) {
        $source = Join-Path $sourceRoot $file
        $destination = Join-Path $destinationRoot $file
        if ((Test-Path -LiteralPath $destination) -and
            (Get-FileHash -LiteralPath $source).Hash -ne (Get-FileHash -LiteralPath $destination).Hash) {
            if ($previousVersions[$file] -ne (Get-FileHash -LiteralPath $destination).Hash) {
                throw "An edited file already exists: $destination. Review it before installing."
            }
        }
    }
    foreach ($file in $files) {
        $source = Join-Path $sourceRoot $file
        $destination = Join-Path $destinationRoot $file
        if ($source -ne $destination) {
            if ((Test-Path -LiteralPath $destination) -and
                (Get-FileHash -LiteralPath $source).Hash -ne (Get-FileHash -LiteralPath $destination).Hash) {
                $backup = Join-Path $destinationRoot ('local-tests/wifi-upgrade-backup/' + $file)
                New-Item -ItemType Directory -Force -Path (Split-Path $backup -Parent) | Out-Null
                if (-not (Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $destination -Destination $backup }
            }
            New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
            Copy-Item -LiteralPath $source -Destination $destination
        }
    }
    $attributes = Join-Path $destinationRoot '.gitattributes'
    $existing = if (Test-Path -LiteralPath $attributes) { [IO.File]::ReadAllText($attributes) } else { '' }
    if ($existing -notmatch '(?m)^firmware/bricq-wifi text eol=lf\r?$') {
        [IO.File]::WriteAllText($attributes, $existing.TrimEnd() + [Environment]::NewLine + 'firmware/bricq-wifi text eol=lf' + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
    }
    Write-Host "Copied USB Wi-Fi files into $destinationRoot. Nothing was staged or committed."
}
Get-Command ssh,scp -ErrorAction Stop | Out-Null
$remoteDir = 'bricq-usb-setup-' + [Guid]::NewGuid().ToString('N')
& ssh -o "HostName=$UsbAddress" -o ConnectTimeout=10 -l $AdminUser bricq "mkdir -m 700 $remoteDir"
if ($LASTEXITCODE -ne 0) { throw 'Cannot access the Pi administrator account over USB.' }
$uploads = @('usb-wifi.py', 'bricq', 'bricq-wifi', 'install-usb-wifi.sh') | ForEach-Object { Join-Path $sourceRoot "firmware/$_" }
& scp -o "HostName=$UsbAddress" -o "User=$AdminUser" @uploads ("bricq:" + $remoteDir + '/')
if ($LASTEXITCODE -ne 0) { throw 'Wi-Fi helper upload failed.' }
& ssh -t -o "HostName=$UsbAddress" -l $AdminUser bricq "cd $remoteDir && bash -n install-usb-wifi.sh && sudo bash install-usb-wifi.sh"
if ($LASTEXITCODE -ne 0) { throw 'USB Wi-Fi helper installation failed. Inspect the output before retrying.' }
& (Join-Path $PSScriptRoot 'install-windows-command.ps1')
Write-Host 'Ready: bricq wifi connects; bricq wifi off disconnects Pi Wi-Fi.'
