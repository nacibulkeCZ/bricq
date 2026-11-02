$ErrorActionPreference = 'Stop'
& ssh bricq 'bricq update'
if ($LASTEXITCODE -ne 0) { throw 'BRICQ update failed or was deferred; inspect the output.' }
