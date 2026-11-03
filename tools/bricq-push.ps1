# Push the local firmware/ tree to the Pi over USB (preferred) or Wi-Fi (fallback).
# Shells out through Invoke-Ssh/Scp/Tar so tests can mock those seams.

# AddressFamily=inet pins resolution to IPv4. mDNS returns both A and AAAA for
# bricq.local; without this, Windows OpenSSH will prefer the AAAA record, which
# on some networks is a public IPv6 that either rejects the key or silently
# routes to the wrong host and makes the install step fail with no output.
$script:CommonSshOpts = @('-o', 'AddressFamily=inet')

function Invoke-Ssh {
    param([string[]]$Arguments)
    & ssh @Arguments
    return $LASTEXITCODE
}

function Invoke-Scp {
    param([string[]]$Arguments)
    & scp @Arguments
    return $LASTEXITCODE
}

function Invoke-Tar {
    param([string[]]$Arguments)
    & tar @Arguments
    return $LASTEXITCODE
}

function Test-BricqUsb {
    param(
        [Parameter(Mandatory)][string]$UsbAddress,
        [int]$TimeoutSeconds = 3
    )
    $exit = Invoke-Ssh ($script:CommonSshOpts + @(
        '-o', "HostName=$UsbAddress",
        '-o', "ConnectTimeout=$TimeoutSeconds",
        '-o', 'BatchMode=yes',
        'bricq', 'true'
    ))
    return $exit -eq 0
}

function Invoke-BricqPush {
    param(
        [Parameter(Mandatory)][string]$UsbAddress,
        [Parameter(Mandatory)][string]$RepoRoot
    )
    $firmware = Join-Path $RepoRoot 'firmware'
    if (-not (Test-Path -LiteralPath $firmware)) {
        throw "firmware directory not found at $firmware"
    }

    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $filename = "bricq-push-$timestamp.tar.gz"
    $localTarball = Join-Path $env:TEMP $filename
    $remotePath = "/tmp/$filename"

    $tarExit = Invoke-Tar @('-czf', $localTarball, '-C', $RepoRoot, 'firmware')
    if ($tarExit -ne 0) { throw 'tar failed to pack firmware/' }

    try {
        $useUsb = Test-BricqUsb -UsbAddress $UsbAddress
        $transport = $script:CommonSshOpts
        if ($useUsb) { $transport += @('-o', "HostName=$UsbAddress") }
        $label = if ($useUsb) { "USB ($UsbAddress)" } else { 'Wi-Fi (SSH alias, IPv4)' }
        Write-Host "bricq push: transport = $label"

        $scpExit = Invoke-Scp ($transport + @($localTarball, "bricq:$remotePath"))
        if ($scpExit -ne 0) { throw "scp upload failed (exit $scpExit)" }

        # Remove the remote tarball only on a successful install so a failed
        # push leaves the tarball behind for manual debugging.
        $sshExit = Invoke-Ssh ($transport + @('bricq', "bricq install-local $remotePath && rm -f $remotePath"))
        if ($sshExit -ne 0) {
            $retry = "ssh -4 bricq 'bricq install-local $remotePath'"
            throw "remote install failed (exit $sshExit). Tarball kept at ${remotePath}; retry manually to see the Pi's error: $retry"
        }

        Write-Host "bricq push: installed from $remotePath"
    } finally {
        Remove-Item -LiteralPath $localTarball -ErrorAction SilentlyContinue
    }
}
