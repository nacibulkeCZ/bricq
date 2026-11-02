"""Interactive Wi-Fi enrollment over the existing USB network; no robot imports."""
import base64
import binascii
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

NMCLI = '/usr/bin/nmcli'
WIFI = 'wlan0'


def decode_ssid(encoded):
    if len(encoded) > 44:
        raise ValueError('Wi-Fi names must be at most 32 UTF-8 bytes.')
    raw = base64.b64decode(encoded, validate=True)
    name = raw.decode('utf-8')
    if not 1 <= len(raw) <= 32 or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise ValueError('Unsupported Wi-Fi name.')
    return name


def query(*args):
    return subprocess.check_output(
        [NMCLI, '--colors', 'no', '--escape', 'no', *args],
        text=True, timeout=20,
    ).strip()


def restore(previous):
    if previous and previous != '--':
        print('Trying to restore the previously active Wi-Fi profile...', flush=True)
        result = subprocess.run(
            [NMCLI, '--wait', '40', 'connection', 'up', 'uuid', previous, 'ifname', WIFI],
            timeout=50,
        )
        if result.returncode:
            print('Previous Wi-Fi could not be restored. USB access remains available.')


def connect(ssid):
    # Refuse to switch Wi-Fi unless the independent USB network link is up.
    if Path('/sys/class/net/usb0/carrier').read_text().strip() != '1':
        raise RuntimeError('Connect the USB data cable first; usb0 is not linked.')
    if query('-g', 'GENERAL.TYPE', 'device', 'show', WIFI) != 'wifi':
        raise RuntimeError('Expected the Pi Wi-Fi interface wlan0.')
    previous = query('-g', 'GENERAL.CON-UUID', 'device', 'show', WIFI)
    print('Connect BRICQ to Wi-Fi ' + json.dumps(ssid, ensure_ascii=False) + '?')
    print('This changes Wi-Fi only. The USB connection is kept.')
    if input('Continue? [y/N] ').strip().lower() not in ('y', 'yes'):
        print('Cancelled; no Wi-Fi settings changed.')
        return
    subprocess.run([NMCLI, 'radio', 'wifi', 'on'], check=True, timeout=20)
    print('If requested, enter the Wi-Fi password below. It will not be displayed.', flush=True)
    try:
        # The password is handled by nmcli on the SSH terminal, never by this script,
        # command-line arguments, Windows files, Git, or our logging.
        result = subprocess.run(
            [NMCLI, '--colors', 'no', '--ask', '--wait', '60',
             'device', 'wifi', 'connect', ssid, 'ifname', WIFI],
            timeout=180,
        )
        if result.returncode:
            raise RuntimeError('Wi-Fi connection failed. Check the password and 2.4 GHz availability.')
        active = query('-g', 'GENERAL.CON-UUID', 'device', 'show', WIFI)
        actual = query('-g', '802-11-wireless.ssid', 'connection', 'show', 'uuid', active)
        if actual != ssid:
            raise RuntimeError('The active Wi-Fi network does not match the requested network.')
        address = query('-g', 'IP4.ADDRESS', 'device', 'show', WIFI)
        print('Connected to ' + json.dumps(ssid, ensure_ascii=False))
        print('Wi-Fi IPv4: ' + (address or 'not assigned'))
        print('NetworkManager saved the profile on the Pi for future connections.')
        print('Association does not guarantee internet access (for example, a hotel login portal).')
    except (RuntimeError, subprocess.SubprocessError, KeyboardInterrupt):
        restore(previous)
        raise


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run through sudo and the installed bricq-wifi launcher.')
    if len(sys.argv) != 2:
        raise ValueError('Exactly one base64-encoded Wi-Fi name is required.')
    ssid = decode_ssid(sys.argv[1])
    if not sys.stdin.isatty():
        raise RuntimeError('An interactive SSH terminal is required (ssh -t).')
    # Fixed root-owned lock: two clients cannot switch Wi-Fi concurrently.
    with open('/run/bricq-wifi.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another Wi-Fi setup is running.')
        connect(ssid)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, binascii.Error, subprocess.SubprocessError) as error:
        print('BRICQ Wi-Fi: ' + str(error), file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print('\nBRICQ Wi-Fi setup cancelled.', file=sys.stderr)
        sys.exit(130)
