[CmdletBinding()]
param(
    [ValidateSet('wifi','status','login')][string]$Command = 'status',
    [ValidateSet('on','off','manual')][string]$Action = 'on'
)
$ErrorActionPreference = 'Stop'
$usb = '10.12.194.1'
try {
    if ($Command -eq 'login') { & ssh -o "HostName=$usb" bricq; exit $LASTEXITCODE }
    if ($Command -eq 'status') { & ssh -o "HostName=$usb" bricq 'bricq status'; exit $LASTEXITCODE }
    if ($Action -eq 'off') {
        & ssh -o "HostName=$usb" -o ConnectTimeout=10 bricq 'sudo -n /usr/local/sbin/bricq-wifi --off'
        exit $LASTEXITCODE
    }
    if ($Action -eq 'manual') { & "$PSScriptRoot\connect-usb-wifi.ps1"; exit 0 }
    if (-not ('Bricq.WindowsWifi' -as [type])) {
        if ($PSVersionTable.PSVersion.Major -le 5) {
            Add-Type -Path "$PSScriptRoot\WindowsWifi.cs" -ReferencedAssemblies System.Xml.dll,System.dll
        } else { Add-Type -Path "$PSScriptRoot\WindowsWifi.cs" }
    }
    $network = [Bricq.WindowsWifi]::Current()
    Write-Host ('Laptop Wi-Fi: ' + $network.Name)
    $answer = Read-Host 'Share this saved Wi-Fi connection with BRICQ over USB? [y/N]'
    if ($answer -notin @('y','yes')) { Write-Host 'Cancelled.'; exit 0 }
    # Check whether BRICQ already has this connection before requesting a saved key.
    $encoded = [Convert]::ToBase64String($network.Ssid)
    & ssh -o "HostName=$usb" -o ConnectTimeout=10 bricq "sudo -n /usr/local/sbin/bricq-wifi --check $encoded"
    if ($LASTEXITCODE -eq 0) { exit 0 }
    if ($LASTEXITCODE -ne 3) { throw 'Cannot check BRICQ. Verify USB access and update the Pi Wi-Fi helper first.' }
    $psk = [Bricq.WindowsWifi]::ReadPsk($network)
    $payload = @{ssid=$encoded; psk=$psk} | ConvertTo-Json -Compress
    try {
        # ASCII-only JSON goes over the SSH stdin pipe, not arguments or disk.
        # No PTY: a remote terminal must never echo the payload.
        $payload | & ssh -T -o "HostName=$usb" -o ConnectTimeout=10 bricq 'sudo -n /usr/local/sbin/bricq-wifi --json'
        $result = $LASTEXITCODE
    } finally { $payload = $null; $psk = $null; $network = $null }
    if ($result -ne 0) { throw 'Wi-Fi setup failed. Check the Pi message above; USB access remains available.' }
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
