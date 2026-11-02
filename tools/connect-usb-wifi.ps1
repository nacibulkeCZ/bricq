[CmdletBinding()]
param(
    [string]$Ssid,
    [string]$UsbAddress = '10.12.194.1'
)
$ErrorActionPreference = 'Stop'
if ($UsbAddress -notmatch '^[0-9]{1,3}(\.[0-9]{1,3}){3}$') { throw 'Use the Pi USB IPv4 address.' }
Get-Command ssh -ErrorAction Stop | Out-Null
if (-not $Ssid) {
    # netsh can be denied by Windows location/privacy permissions; manual entry
    # remains available without changing those settings.
    $lines = & netsh wlan show interfaces 2>&1
    $names = @($lines | ForEach-Object {
        if ("$_" -match '^\s*SSID\s*:\s*(.+?)\s*$') { $Matches[1] }
    } | Select-Object -Unique)
    if ($names.Count -eq 1) {
        $Ssid = $names[0]
        Write-Host "Laptop Wi-Fi detected: $Ssid"
    } else {
        $Ssid = Read-Host 'Enter the Wi-Fi name (SSID) to connect BRICQ to'
    }
}
$bytes = [Text.Encoding]::UTF8.GetBytes($Ssid)
if ($bytes.Length -lt 1 -or $bytes.Length -gt 32 -or $Ssid -match '[\x00-\x1f\x7f]') {
    throw 'The Wi-Fi name must contain 1-32 UTF-8 bytes and no control characters.'
}
$encoded = [Convert]::ToBase64String($bytes)
Write-Host 'Connecting through USB. Confirm the network on the Pi, then enter its Wi-Fi password if asked.'
Write-Host 'The Pi Zero W needs a 2.4 GHz network. Keep its USB cable connected.'
& ssh -t -o "HostName=$UsbAddress" -o ConnectTimeout=10 bricq "sudo -n /usr/local/sbin/bricq-wifi $encoded"
if ($LASTEXITCODE -ne 0) { throw 'Wi-Fi setup did not complete. Check the message above; the USB link is unchanged.' }
