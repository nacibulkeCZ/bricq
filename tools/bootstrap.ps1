[CmdletBinding()]
param([string]$Address = 'bricq.local', [string]$ExistingUser = 'stepanek', [switch]$Resume)
$ErrorActionPreference = 'Stop'
if ($Address -notmatch '^[a-zA-Z0-9.-]+$' -or $ExistingUser -notmatch '^[a-z_][a-z0-9_-]*$') { throw 'Invalid address or account name.' }
$repo = Split-Path $PSScriptRoot -Parent
foreach ($program in @('ssh', 'scp', 'tar', 'git')) { Get-Command $program -ErrorAction Stop | Out-Null }
& git -C $repo check-ignore local-tests/probe | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'local-tests must be ignored before downloading.' }
$target = $ExistingUser + '@' + $Address
Write-Host 'Inspecting the Pi without starting any robot scripts...'
& ssh $target 'uname -m; cat /etc/os-release; python3 --version; ls -l ~/*.py; command -v git; command -v systemctl'
if ($LASTEXITCODE -ne 0) { throw 'Inspection failed. Check SSH and required commands.' }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupName = "bricq-tests-$stamp.tar.gz"
$remoteDir = "bricq-install-$stamp"
& ssh $target "mkdir -m 755 $remoteDir"
if ($LASTEXITCODE -ne 0) { throw 'Could not create upload directory.' }
& scp (Join-Path $PSScriptRoot 'backup-tests.py') ($target + ':' + $remoteDir + '/backup-tests.py')
if ($LASTEXITCODE -ne 0) { throw 'Backup helper upload failed; no installation attempted.' }
& ssh $target "python3 $remoteDir/backup-tests.py $backupName"
if ($LASTEXITCODE -ne 0) { throw 'Pi backup failed; no installation attempted.' }
$local = Join-Path $repo "local-tests\pi-$stamp"
New-Item -ItemType Directory -Force -Path $local | Out-Null
$archive = Join-Path $local $backupName
& scp ($target + ':' + $backupName) $archive
if ($LASTEXITCODE -ne 0) { throw 'Backup download failed; no installation attempted.' }
& tar -xzf $archive -C $local
if ($LASTEXITCODE -ne 0) { throw 'Backup extraction failed; no installation attempted.' }
Write-Host "Old Pi scripts downloaded to $local (ignored by Git)."
& "$PSScriptRoot\setup-windows.ps1" -Address $Address -SkipTest
$bundle = Join-Path $env:TEMP "bricq-install-$stamp.tar.gz"
& tar -czf $bundle --exclude=__pycache__ -C $repo firmware
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
& scp $bundle ($target + ':' + $remoteDir + '/install.tar.gz')
if ($LASTEXITCODE -ne 0) { throw 'Firmware upload failed.' }
$publicKey = Join-Path $env:USERPROFILE '.ssh\bricq_ed25519.pub'
& scp $publicKey ($target + ':' + $remoteDir + '/computer.pub')
if ($LASTEXITCODE -ne 0) { throw 'Public key upload failed.' }
Write-Host 'Installing the bricq account and status-only service. sudo may ask for your existing Pi password.'
$resumeFlag = if ($Resume) { ' --resume' } else { '' }
& ssh -t $target "cd $remoteDir && tar -xzf install.tar.gz && bash -n firmware/install.sh && bash -n firmware/login.sh && sudo bash firmware/install.sh computer.pub$resumeFlag"
if ($LASTEXITCODE -ne 0) { throw 'Installation did not finish. Keep the existing account and inspect the printed error before retrying.' }
& ssh bricq 'bricq status'
if ($LASTEXITCODE -ne 0) { throw 'New login verification failed. The old account and backups remain available.' }
Write-Host 'Ready. From now on use: ssh bricq'
