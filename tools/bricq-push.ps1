# Push the local firmware/ tree to the Pi over USB (preferred) or Wi-Fi (fallback).
# Shells out through Invoke-Ssh/Scp/Tar so tests can mock those seams.

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
    $exit = Invoke-Ssh @(
        '-o', "HostName=$UsbAddress",
        '-o', "ConnectTimeout=$TimeoutSeconds",
        '-o', 'BatchMode=yes',
        'bricq', 'true'
    )
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
        $override = if ($useUsb) { @('-o', "HostName=$UsbAddress") } else { @() }
        $label = if ($useUsb) { "USB ($UsbAddress)" } else { 'Wi-Fi (SSH alias)' }
        Write-Host "bricq push: transport = $label"

        $scpExit = Invoke-Scp ($override + @($localTarball, "bricq:$remotePath"))
        if ($scpExit -ne 0) { throw 'scp upload failed' }

        $sshExit = Invoke-Ssh ($override + @('bricq', "bricq install-local $remotePath"))
        if ($sshExit -ne 0) { throw 'remote install failed' }

        Write-Host "bricq push: installed from $remotePath"
    } finally {
        Remove-Item -LiteralPath $localTarball -ErrorAction SilentlyContinue
    }
}
