[CmdletBinding()]
param([string]$Address = 'bricq.local', [switch]$SkipTest)
$ErrorActionPreference = 'Stop'
if ($Address -notmatch '^[a-zA-Z0-9.-]+$') { throw 'Use a hostname or IPv4 address.' }
foreach ($program in @('ssh', 'ssh-keygen', 'ssh-add')) { Get-Command $program -ErrorAction Stop | Out-Null }
$sshDir = Join-Path $env:USERPROFILE '.ssh'
New-Item -ItemType Directory -Force -Path $sshDir | Out-Null
$key = Join-Path $sshDir 'bricq_ed25519'
if (-not (Test-Path -LiteralPath $key)) {
    Write-Host 'Create a key for this computer. Choose a passphrase at the prompt.'
    & ssh-keygen -t ed25519 -f $key -C "bricq-$env:COMPUTERNAME"
    if ($LASTEXITCODE -ne 0) { throw 'Key generation failed.' }
}
if (-not (Test-Path -LiteralPath "$key.pub")) { throw 'Public key is missing; inspect the existing key pair.' }
$config = Join-Path $sshDir 'config'
$text = if (Test-Path -LiteralPath $config) { [IO.File]::ReadAllText($config) } else { '' }
$clean = [regex]::Replace($text, '(?ms)^# BEGIN BRICQ\r?\n.*?^# END BRICQ\r?\n?', '')
if ($clean -match '(?im)^\s*Host\s+[^\r\n]*\bbricq\b') { throw 'An unmanaged bricq alias exists. Review it before setup.' }
# AddressFamily inet forces IPv4; mDNS for bricq.local returns both A and AAAA,
# and Windows OpenSSH prefers AAAA — which on some networks routes to a public
# IPv6 that silently rejects the key and makes bricq push fail with no output.
$block = @"
# BEGIN BRICQ
Host bricq
    HostName $Address
    User bricq
    IdentityFile ~/.ssh/bricq_ed25519
    IdentitiesOnly yes
    AddressFamily inet
    ServerAliveInterval 30
    ServerAliveCountMax 3
# END BRICQ

"@
if (Test-Path -LiteralPath $config) {
    Copy-Item -LiteralPath $config -Destination "$config.bricq-backup-$([guid]::NewGuid().ToString('N'))"
}
[IO.File]::WriteAllText($config, $block + $clean, [Text.UTF8Encoding]::new($false))
Write-Host 'Mandatory SSH alias configured: ssh bricq'
# Enable Windows OpenSSH ssh-agent so the key passphrase is only ever typed
# once per computer. Keys are DPAPI-encrypted in the registry and auto-reloaded
# after reboot by the Automatic-start service.
$agent = Get-Service ssh-agent -ErrorAction SilentlyContinue
if (-not $agent) {
    Write-Warning 'ssh-agent service missing; install the "OpenSSH Client" Windows feature to enable passphrase caching.'
} else {
    $needsAdmin = $agent.StartType -ne 'Automatic' -or $agent.Status -ne 'Running'
    if ($needsAdmin) {
        Write-Host 'Enabling ssh-agent service (one UAC prompt)...'
        $script = 'Set-Service ssh-agent -StartupType Automatic; Start-Service ssh-agent'
        $p = Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList @('-NoProfile', '-Command', $script)
        if ($p.ExitCode -ne 0) { throw 'ssh-agent service could not be enabled. Re-run setup-windows.ps1 after approving the UAC prompt.' }
    }
    $loaded = (& ssh-add -l 2>$null) -join "`n"
    $fingerprint = (& ssh-keygen -lf $key 2>$null) -split '\s+' | Select-Object -Index 1
    if ($fingerprint -and $loaded -notmatch [regex]::Escape($fingerprint)) {
        Write-Host 'Caching key passphrase in ssh-agent (type it once; it will be remembered across reboots):'
        & ssh-add $key
        if ($LASTEXITCODE -ne 0) { throw 'ssh-add failed; the key passphrase was not cached.' }
    }
}
Write-Host "This computer's public key: $key.pub"
if (-not $SkipTest) {
    & ssh bricq 'bricq status'
    if ($LASTEXITCODE -ne 0) { throw 'Login failed. An existing owner must authorize a new computer public key first. See docs/startup-firmware-documentation.md.' }
}
