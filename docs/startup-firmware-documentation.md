# BRICQ startup firmware

This is the software foundation for the Raspberry Pi Zero W: a neutral login, a background application, and updates from GitHub. The application currently reports status only; it does not move servos. The original servo panel and Python environment remain separate.

## How it works

1. **Boot:** Linux starts `bricq.service`, which runs the installed application as the `bricq` user.
2. **Login:** `ssh bricq` connects using your computer's SSH key. The Pi shows the BRICQ banner and status.
3. **Develop:** Edit locally in VS Code, commit, and push to the GitHub repository's `main` branch.
4. **Update:** `bricq update` downloads changed firmware, checks Python syntax, and prepares a separate release with its own Python environment.
5. **Restart:** The manager switches releases and checks `/health`. If startup fails, it attempts to restore the previous release.

Automatic checks are optional and initially disabled. The Pi only needs internet access to download updates; your laptop can be offline. SSH normally requires both devices on the same local network.

## Everyday commands

**On the Pi** (after `ssh bricq`):

| Command | Purpose |
|---|---|
| `bricq status` | Show version, network addresses, and service status. |
| `bricq update` | Install firmware pushed to GitHub. |
| `bricq logs` | Show recent application logs. |
| `bricq rollback` | Restore the previous release. |
| `bricq watch` | Enable background update checks roughly every two minutes. |
| `bricq watch stop` | Disable future checks; an ongoing update may finish. |
| `bricq install-local <path>` | Install from a local tarball or directory (used internally by `bricq push`). |
| `bricq legtest <leg>` | Start the leg-test web UI for one leg (e.g. `bricq legtest front-right`). |

**On Windows** (run from any shell with the `bricq` command installed):

| Command | Purpose |
|---|---|
| `bricq push` | Package your current working tree and install it on the Pi. USB first, falls back to Wi-Fi. |
| `bricq status`, `bricq login`, `bricq wifi` | Current USB-only operations. |

`bricq push` is for the edit-and-test dev loop: when you've changed firmware locally and want to try it on the Pi without going through a Git push + `bricq update`. The same release/health-check/auto-rollback pipeline as `bricq update` runs on the Pi — a push that fails to come up healthy rolls back automatically.

Alternatively, run `./tools/deploy.ps1` from Windows to request an update over SSH.

## Modes

A **mode** is a hardware-driving feature (first one: `legtest`). Only one mode runs at a time. Starting a mode stops `bricq.service` so `/health` honestly reports "not available" and other operations (updates, pushes) refuse while the hardware is live. Exiting the mode (Ctrl+C) restarts `bricq.service` automatically.

| Mode | Command | What it does |
|---|---|---|
| `legtest` | `bricq legtest <leg>` | Flask UI on port 5000 for one leg at a time. Browser URL: `http://bricq.local:5000` (Wi-Fi) or `http://10.12.194.1:5000` (USB). |

Valid leg names: `front-left`, `front-right`, `back-left`, `back-right`. Only legs with channels defined in [firmware/hardware.py](../firmware/hardware.py) `LEGS` are usable; unwired legs error with a clear message.

**Adding a new mode** (future `cameratest`, `walktest`, etc.):

1. Add any new hardware config to `firmware/hardware.py` (pins, calibration constants).
2. Add deps to `firmware/requirements.txt`.
3. Write tests in `firmware/tests/test_mode_<name>.py` using the `FakeServoBus` fixture pattern.
4. Create `firmware/modes/<name>.py` exposing `main(arg)` that blocks on SIGINT.
5. Add the mode name to `manager.py`'s argparse `choices` and dispatch to `run_mode('<name>', arg)`.
6. `bricq push` to try it on real hardware.

## File guide

| File | Role |
|---|---|
| `firmware/app.py` | Status-only application; serves `/health` on port 8765 when no mode is running. |
| `firmware/manager.py` | Handles commands, releases, updates, health checks, rollback, and mode dispatch. |
| `firmware/hardware.py` | Single source of truth for leg wiring (`LEGS`) and the `ServoBus` abstraction. |
| `firmware/modes/legtest.py` | Leg test mode: Flask UI + servo driver for one leg at a time. |
| `firmware/bricq` | Small Linux launcher that passes your command to the manager. |
| `firmware/requirements.txt` | Runtime Python dependencies for the per-release venv. |
| `firmware/login.sh` | Login banner, status display, and terminal prompt. |
| `firmware/install.sh` | Creates the Pi account and installs the management files and services. |
| `firmware/bricq.service` | Starts the application at boot and restarts it after a crash. |
| `firmware/bricq-watch.service` | Runs one update check. |
| `firmware/bricq-watch.timer` | Schedules update checks when enabled. |
| `tools/setup-windows.ps1` | Creates the computer's SSH key and mandatory `bricq` alias; enables ssh-agent and caches the passphrase so every subsequent command runs silently. |
| `tools/bootstrap.ps1` | Coordinates initial installation from Windows. |
| `tools/backup-tests.py` | Archives old Pi scripts without running them. |
| `tools/deploy.ps1` | Runs `bricq update` through SSH. |
| `tools/bricq-push.ps1` | Packages the local `firmware/` tree and installs it on the Pi over USB or Wi-Fi. |
| `firmware/tests/` | pytest suite for `manager.py`. Run from repo root with `pytest`. |
| `tools/tests/` | Pester suite for Windows tools. Run from PowerShell with `Invoke-Pester -Path .\tools\tests`. |
| `.gitignore` | Excludes local backups, environments, caches, and common credential files. |
| `.gitattributes` | Keeps Windows/Linux file line endings compatible. |

## Setup and boundaries

**Fresh installation:** run `./tools/bootstrap.ps1 -Address bricq.local` in Windows PowerShell. It backs up old scripts into ignored `local-tests/` before installing. The Pi needs Git, systemd, sudo, Python 3.9+, and `python3-venv`. `-Resume` is only for a verified incomplete installation.

**New computer:** run `./tools/setup-windows.ps1 -SkipTest`. Have the owner authorize its public key in the Pi's `~/.ssh/authorized_keys`, then use `ssh bricq`. Keep private keys on their computer. Use `-Address` with the Pi's current IP if hostname discovery fails.

**Updates:** downloaded releases live under `~/.local/share/bricq/`. Application updates do not replace the installed manager, login script, or systemd configuration; those require administrator maintenance. Updates to an active application currently require confirmed healthy, disarmed, status-only operation.

USB Wi-Fi onboarding and robot motion control are future additions.
