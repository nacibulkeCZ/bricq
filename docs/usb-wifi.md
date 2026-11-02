# BRICQ Wi-Fi over USB

See [system requirements and USB driver installation](requirements.md) before setup.

Connect the Pi's USB data port to a computer with the Raspberry Pi RNDIS driver and
an authorized BRICQ SSH key. Run these commands in **Windows PowerShell**:

| Command | Action |
|---|---|
| bricq wifi | Confirm and share the laptop's current saved Wi-Fi network with the Pi. |
| bricq wifi off | Turn off the Pi's Wi-Fi radio; keep USB and saved profiles. |
| bricq wifi manual | Enter a Wi-Fi name/password manually through the SSH terminal. |
| bricq status | Show Pi status through USB. |
| bricq login | Open the Pi's shell through USB. |

Inside the Pi's SSH shell, bricq wifi off also turns Wi-Fi off; bricq wifi on
enables the radio and allows reconnection to saved networks. Plain bricq wifi
on the Pi asks for a network name and, if necessary, its password. Automatic
laptop-password sharing runs on Windows because the key is stored there.
The Pi launcher and helper require this installer update; bricq update alone
does not replace installed management tools.

Automatic setup detects the current network through the Windows WLAN API. After confirmation,
it checks whether the Pi is already connected. If needed, Windows retrieves the saved key
and sends a derived WPA key over encrypted SSH stdin, without a terminal that could echo it.
Secrets are not written to Windows files, passed as arguments, printed, or stored in Git.
The Pi saves the key in a root-only NetworkManager profile for automatic reconnection.

Windows may require an Administrator PowerShell to read the saved password. It may also
restrict Wi-Fi detection through its privacy settings. The helper reports those restrictions;
it does not change them. SSH can still ask for your key's passphrase.
Automatic sharing currently supports WPA/WPA2 Personal, with a UTF-8 SSID and a 2.4 GHz
network available to the Zero W. Enterprise, WPA3-only, open-network enrollment and
captive-portal login are outside this initial flow.

Joining a different network changes only wlan0. The USB link remains available, and the
helper attempts to restore the previous Wi-Fi profile on failure. Turning Wi-Fi off does
not affect the laptop's Wi-Fi. Run bricq wifi to turn the Pi radio on and reconnect.

## Install or upgrade

From the repository in Windows PowerShell:

    .\tools\install-usb-wifi.ps1

The owner account installs the root-owned Pi helper and its restricted sudo rule.
The installer also registers the Windows command in the current user's PATH.
For a new computer, first authorize its SSH key, then run:

    .\tools\install-windows-command.ps1

Restart other terminal applications if they do not yet see the new command.
The Windows command uses USB address 10.12.194.1 (official gadget shared mode).
It does not require the Pi to be connected to Wi-Fi.

## Files

| File | Purpose |
|---|---|
| tools/bricq.cmd | Short Windows command launcher. |
| tools/bricq-cli.ps1 | Dispatch commands and send Wi-Fi credentials through SSH. |
| tools/WindowsWifi.cs | Read the current Windows Wi-Fi profile using native APIs. |
| tools/install-windows-command.ps1 | Install the launcher for this Windows user. |
| tools/connect-usb-wifi.ps1 | Manual Wi-Fi setup fallback. |
| tools/install-usb-wifi.ps1 | Install/upgrade both sides, preserving recognized old files. |
| firmware/usb-wifi.py | Manage Pi Wi-Fi, saved profiles, status and disconnect. |
| firmware/bricq-wifi | Launch the Python helper in isolated mode. |
| firmware/install-usb-wifi.sh | Install the Pi helper and narrowly scoped sudo permission. |

These management files are maintained separately from automatic application updates.
