# Behavioral tests for bricq push.
# Design: push logic lives in tools/bricq-push.ps1 as named functions. Tests
# mock Invoke-Ssh/Invoke-Scp/Invoke-Tar at the function seam, so native EXE
# invocation is isolated. Pester 5+ compatible.

BeforeAll {
    . (Join-Path $PSScriptRoot '..\bricq-push.ps1')

    $script:fakeRepo = Join-Path $TestDrive 'repo'
    New-Item -ItemType Directory -Path (Join-Path $fakeRepo 'firmware') -Force | Out-Null
    'print("hi")' | Set-Content -Path (Join-Path $fakeRepo 'firmware\app.py')
    '' | Set-Content -Path (Join-Path $fakeRepo 'firmware\requirements.txt')
}

Describe 'Invoke-BricqPush' {
    BeforeEach {
        Mock -CommandName Invoke-Tar -MockWith { 0 }
        Mock -CommandName Invoke-Scp -MockWith { 0 }
        Mock -CommandName Invoke-Ssh -MockWith { 0 }
    }

    Context 'when USB is reachable' {
        BeforeEach {
            # Default Invoke-Ssh mock already returns 0, so Test-BricqUsb reports reachable.
        }

        It 'tars the firmware directory from the repo root' {
            Invoke-BricqPush -UsbAddress '10.12.194.1' -RepoRoot $fakeRepo
            Should -Invoke -CommandName Invoke-Tar -Times 1 -ParameterFilter {
                ($Arguments -join ' ') -match '-C' -and
                ($Arguments -join ' ') -match [regex]::Escape($fakeRepo) -and
                ($Arguments -join ' ') -match '(^|\s)firmware($|\s)'
            }
        }

        It 'uses USB HostName override for scp upload' {
            Invoke-BricqPush -UsbAddress '10.12.194.1' -RepoRoot $fakeRepo
            Should -Invoke -CommandName Invoke-Scp -Times 1 -ParameterFilter {
                ($Arguments -join ' ') -match 'HostName=10\.12\.194\.1'
            }
        }

        It 'uses USB HostName override for the ssh install call' {
            Invoke-BricqPush -UsbAddress '10.12.194.1' -RepoRoot $fakeRepo
            Should -Invoke -CommandName Invoke-Ssh -Times 1 -ParameterFilter {
                ($Arguments -join ' ') -match 'HostName=10\.12\.194\.1' -and
                ($Arguments -join ' ') -match 'install-local'
            }
        }

        It 'invokes install-local with the uploaded tarball path on the Pi' {
            Invoke-BricqPush -UsbAddress '10.12.194.1' -RepoRoot $fakeRepo
            Should -Invoke -CommandName Invoke-Ssh -Times 1 -ParameterFilter {
                ($Arguments -join ' ') -match 'bricq install-local /tmp/bricq-push-'
            }
        }

        It 'aborts the push if tar fails' {
            Mock -CommandName Invoke-Tar -MockWith { 1 }
            { Invoke-BricqPush -UsbAddress '10.12.194.1' -RepoRoot $fakeRepo } | Should -Throw
            Should -Invoke -CommandName Invoke-Scp -Times 0
            Should -Invoke -CommandName Invoke-Ssh -Times 0 -ParameterFilter {
                ($Arguments -join ' ') -match 'install-local'
            }
        }

        It 'aborts if scp fails' {
            Mock -CommandName Invoke-Scp -MockWith { 1 }
            { Invoke-BricqPush -UsbAddress '10.12.194.1' -RepoRoot $fakeRepo } | Should -Throw
            Should -Invoke -CommandName Invoke-Ssh -Times 0 -ParameterFilter {
                ($Arguments -join ' ') -match 'install-local'
            }
        }
    }

    Context 'when USB probe fails' {
        BeforeEach {
            Mock -CommandName Invoke-Ssh -ParameterFilter {
                ($Arguments -join ' ') -match 'ConnectTimeout='
            } -MockWith { 255 }
        }

        It 'does not pass USB HostName override to scp' {
            Invoke-BricqPush -UsbAddress '10.12.194.1' -RepoRoot $fakeRepo
            Should -Invoke -CommandName Invoke-Scp -Times 1 -ParameterFilter {
                -not (($Arguments -join ' ') -match 'HostName=')
            }
        }

        It 'does not pass USB HostName override to the ssh install call' {
            Invoke-BricqPush -UsbAddress '10.12.194.1' -RepoRoot $fakeRepo
            Should -Invoke -CommandName Invoke-Ssh -Times 1 -ParameterFilter {
                ($Arguments -join ' ') -match 'install-local' -and
                -not (($Arguments -join ' ') -match 'HostName=')
            }
        }
    }
}

Describe 'Test-BricqUsb' {
    BeforeEach {
        Mock -CommandName Invoke-Ssh -MockWith { 0 }
    }

    It 'returns true when ssh probe exits 0' {
        Test-BricqUsb -UsbAddress '10.12.194.1' | Should -BeTrue
    }

    It 'returns false when ssh probe exits non-zero' {
        Mock -CommandName Invoke-Ssh -MockWith { 255 }
        Test-BricqUsb -UsbAddress '10.12.194.1' | Should -BeFalse
    }

    It 'passes ConnectTimeout and BatchMode to ssh' {
        Test-BricqUsb -UsbAddress '10.12.194.1' -TimeoutSeconds 3 | Out-Null
        Should -Invoke -CommandName Invoke-Ssh -Times 1 -ParameterFilter {
            ($Arguments -join ' ') -match 'ConnectTimeout=3' -and
            ($Arguments -join ' ') -match 'BatchMode=yes'
        }
    }
}
