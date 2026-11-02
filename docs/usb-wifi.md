# Wi-Fi setup over USB

The Pi Zero W uses Raspberry Pi OS Trixie and the official rpi-usb-gadget package.
USB networking is already enabled. Connect a data cable to the USB port nearest HDMI.
Windows needs the official Raspberry Pi RNDIS driver once per computer.

## Install the Wi-Fi helper once

From the project folder in Windows PowerShell:

    .\tools\install-usb-wifi.ps1

This uses the existing administrator account to install a root-owned helper and grant
the bricq account permission to run that helper only. It does not grant unrestricted
sudo, change USB networking, join Wi-Fi, or restart the robot.
The account's existing SSH authorization is still required.

## Join the laptop's Wi-Fi

    .\tools\connect-usb-wifi.ps1

The script detects the laptop's SSID, connects to BRICQ over USB, and asks for confirmation.
If Windows cannot provide the SSID, enter it manually, or use:

    .\tools\connect-usb-wifi.ps1 -Ssid 'My Wi-Fi'

Enter the Wi-Fi password at the Pi's prompt if requested. It is hidden and never passed
as a command argument or saved in this repository. NetworkManager stores the profile
on the Pi so it can reconnect later. Previously saved credentials may avoid a password prompt.

Only wlan0 is changed. USB access remains available if joining fails; the helper attempts
to restore the previously active Wi-Fi profile. The Zero W needs 2.4 GHz Wi-Fi.
Enterprise networks and captive-portal login are outside this helper's initial scope.
Connecting to Wi-Fi does not by itself guarantee internet access.

The default USB Pi address is 10.12.194.1. If Internet Connection Sharing changes it,
pass the actual USB address using -UsbAddress. No administrator account is needed for
everyday use after installation: the helper connects as bricq with the computer's SSH key.

| File | Purpose |
|---|---|
| tools/connect-usb-wifi.ps1 | Detect SSID and launch the interactive setup over USB. |
| tools/install-usb-wifi.ps1 | Upload and install the helper using the owner account. |
| firmware/usb-wifi.py | Confirm the network and manage Wi-Fi through NetworkManager. |
| firmware/bricq-wifi | Launch the Python helper in isolated mode. |
| firmware/install-usb-wifi.sh | Install helper files and the narrow sudo permission. |

These management files are installed separately from ordinary application updates.
