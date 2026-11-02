[CmdletBinding()]
param([string]$Address = 'bricq.local', [switch]$SkipTest)
$ErrorActionPreference = 'Stop'
if ($Address -notmatch '^[a-zA-Z0-9.-]+$') { throw 'Use a hostname or IPv4 address.' }
foreach ($program in @('ssh', 'ssh-keygen')) { Get-Command $program -ErrorAction Stop | Out-Null }
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
$block = @"
# BEGIN BRICQ
Host bricq
    HostName $Address
    User bricq
    IdentityFile ~/.ssh/bricq_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
# END BRICQ

"@
if (Test-Path -LiteralPath $config) {
    Copy-Item -LiteralPath $config -Destination "$config.bricq-backup-$([guid]::NewGuid().ToString('N'))"
}
[IO.File]::WriteAllText($config, $block + $clean, [Text.UTF8Encoding]::new($false))
Write-Host 'Mandatory SSH alias configured: ssh bricq'
Write-Host "This computer's public key: $key.pub"
if (-not $SkipTest) {
    & ssh bricq 'bricq status'
    if ($LASTEXITCODE -ne 0) { throw 'Login failed. An existing owner must authorize a new computer public key first. See docs/startup-firmware-documentation.md.' }
}
