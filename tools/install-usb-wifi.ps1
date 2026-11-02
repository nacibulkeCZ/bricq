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
    'firmware/usb-wifi.py', 'firmware/bricq-wifi', 'firmware/install-usb-wifi.sh', 'docs/usb-wifi.md')
if ($ProjectPath) {
    $destinationRoot = (Resolve-Path -LiteralPath $ProjectPath).Path
    if (-not (Test-Path -LiteralPath (Join-Path $destinationRoot '.git'))) { throw 'ProjectPath must be the existing Git repository.' }
    # Check every destination before copying anything; preserve user edits.
    foreach ($file in $files) {
        $source = Join-Path $sourceRoot $file
        $destination = Join-Path $destinationRoot $file
        if ((Test-Path -LiteralPath $destination) -and
            (Get-FileHash -LiteralPath $source).Hash -ne (Get-FileHash -LiteralPath $destination).Hash) {
            throw "An edited file already exists: $destination. Review it before installing."
        }
    }
    foreach ($file in $files) {
        $source = Join-Path $sourceRoot $file
        $destination = Join-Path $destinationRoot $file
        if ($source -ne $destination) {
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
foreach ($file in @('usb-wifi.py', 'bricq-wifi', 'install-usb-wifi.sh')) {
    & scp -o "HostName=$UsbAddress" -o "User=$AdminUser" (Join-Path $sourceRoot "firmware/$file") ("bricq:" + $remoteDir + '/' + $file)
    if ($LASTEXITCODE -ne 0) { throw "Upload failed: $file" }
}
& ssh -t -o "HostName=$UsbAddress" -l $AdminUser bricq "cd $remoteDir && bash -n install-usb-wifi.sh && sudo bash install-usb-wifi.sh"
if ($LASTEXITCODE -ne 0) { throw 'USB Wi-Fi helper installation failed. Inspect the output before retrying.' }
Write-Host 'Installed. Run tools/connect-usb-wifi.ps1 from your project.'
