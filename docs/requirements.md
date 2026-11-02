# BRICQ requirements

## Windows computer

| Requirement | Purpose |
|---|---|
| Windows PowerShell 5.1 or PowerShell 7 | Run setup scripts; the short command uses Windows PowerShell. |
| OpenSSH Client (ssh, scp, ssh-keygen) | Login, encrypted transfer, and per-computer keys. |
| Raspberry Pi USB RNDIS driver | Recognize the Pi as a USB network adapter. |
| Authorized BRICQ SSH key and alias | Access the Pi through the bricq account. |
| Git | Develop and publish firmware changes; also used by initial bootstrap. |
| tar | Package firmware and extract backups during initial bootstrap. |

### USB driver installation

Download **rpi-usb-gadget-driver-setup.exe** from the
[official Raspberry Pi releases](https://github.com/raspberrypi/rpi-usb-gadget/releases).
Expand **Assets** and run the Windows installer. Install it once on every computer
that will use the robot over USB, including a teacher's computer.

After installation, Windows should show **Raspberry Pi USB Remote NDIS Network Device**
under Network adapters. Restart Windows if the installer requests it.
The driver is a system dependency: it is not installed by pip or bundled in this repository.

## Raspberry Pi

The current USB setup uses Raspberry Pi Zero W, Raspberry Pi OS/Raspbian 13 Trixie,
NetworkManager (nmcli), and the official rpi-usb-gadget package with gadget mode enabled.
BRICQ also needs Python 3.9+, python3-venv, Git, Bash, systemd, sudo, and an SSH server.
The current Python application and Wi-Fi helper use the standard library; Python package
dependencies belong in firmware/requirements.txt.

Use a **micro-USB data cable** in the Pi's **USB** port nearest HDMI, not PWR IN.
The Zero W requires a 2.4 GHz Wi-Fi network. Automatic saved-key sharing currently supports
WPA/WPA2 Personal. Windows must permit access to the saved Wi-Fi key; Administrator
PowerShell may be required. No Wi-Fi password is stored in this repository.
