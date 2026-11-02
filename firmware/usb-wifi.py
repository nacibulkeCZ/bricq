"""Interactive Wi-Fi enrollment over the existing USB network; no robot imports."""
import base64
import binascii
import fcntl
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import uuid

NMCLI = '/usr/bin/nmcli'
WIFI = 'wlan0'


def require_usb():
    if Path('/sys/class/net/usb0/carrier').read_text().strip() != '1':
        raise RuntimeError('Connect the USB data cable first; usb0 is not linked.')


def already_connected(ssid):
    active = query('-g', 'GENERAL.CON-UUID', 'device', 'show', WIFI)
    if active and active != '--':
        actual = query('-g', '802-11-wireless.ssid', 'connection', 'show', 'uuid', active)
        state = query('-g', 'GENERAL.STATE', 'device', 'show', WIFI)
        if actual == ssid and state.startswith('100'):
            print('Already connected to ' + json.dumps(ssid, ensure_ascii=False) + '; no changes needed.')
            print('Wi-Fi IPv4: ' + query('-g', 'IP4.ADDRESS', 'device', 'show', WIFI))
            return True
    return False


def connect_saved(payload):
    if not isinstance(payload, dict) or set(payload) != {'ssid', 'psk'}:
        raise ValueError('Invalid Wi-Fi request.')
    ssid = decode_ssid(payload['ssid'])
    psk = payload['psk']
    if not isinstance(psk, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', psk):
        raise ValueError('Invalid WPA key.')
    if already_connected(ssid):
        return
    previous = query('-g', 'GENERAL.CON-UUID', 'device', 'show', WIFI)
    identifier = str(uuid.uuid4())
    filename = Path('/etc/NetworkManager/system-connections') / ('bricq-' + identifier + '.nmconnection')
    # Numeric SSID bytes and a hex PSK prevent keyfile injection and escaping bugs.
    encoded_ssid = ''.join(str(byte) + ';' for byte in ssid.encode('utf-8'))
    profile = (
        '[connection]\nid=BRICQ-' + identifier + '\nuuid=' + identifier +
        '\ntype=wifi\ninterface-name=wlan0\nautoconnect=true\n'
        '[wifi]\nmode=infrastructure\nssid=' + encoded_ssid +
        '\n[wifi-security]\nkey-mgmt=wpa-psk\npsk=' + psk +
        '\npsk-flags=0\n[ipv4]\nmethod=auto\n[ipv6]\nmethod=auto\n'
    )
    # This is the intentional persistent Wi-Fi profile, readable only by root.
    fd = os.open(str(filename), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as file:
            file.write(profile)
        subprocess.run([NMCLI, 'connection', 'load', str(filename)], check=True, timeout=20)
        subprocess.run([NMCLI, 'radio', 'wifi', 'on'], check=True, timeout=20)
        subprocess.run([NMCLI, '--wait', '60', 'connection', 'up', 'uuid', identifier,
                        'ifname', WIFI], check=True, timeout=75)
        if not already_connected(ssid):
            raise RuntimeError('Requested network did not become active.')
        print('Wi-Fi profile saved on the Pi. USB remains connected.')
    except (OSError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt):
        # Remove only the new profile created by this attempt, then restore the old one.
        subprocess.run([NMCLI, 'connection', 'delete', 'uuid', identifier], timeout=20,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        filename.unlink(missing_ok=True)
        restore(previous)
        raise


def decode_ssid(encoded):
    if not isinstance(encoded, str) or len(encoded) > 44:
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
    if already_connected(ssid):
        return
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
    require_usb()
    # Fixed root-owned lock: two clients cannot switch Wi-Fi concurrently.
    with open('/run/bricq-wifi.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another Wi-Fi setup is running.')
        args = sys.argv[1:]
        if args == ['--off']:
            subprocess.run([NMCLI, 'radio', 'wifi', 'off'], check=True, timeout=20)
            print('Pi Wi-Fi is off. Saved networks are kept; USB access stays available.')
        elif args == ['--on']:
            subprocess.run([NMCLI, 'radio', 'wifi', 'on'], check=True, timeout=20)
            print('Pi Wi-Fi enabled. NetworkManager can reconnect to saved networks.')
        elif args == ['--interactive']:
            if not sys.stdin.isatty():
                raise RuntimeError('Use an interactive SSH terminal.')
            print('On-Pi setup: enter the network name below.')
            print('To share your laptop saved password automatically, run bricq wifi in Windows.')
            ssid = input('Wi-Fi name (SSID): ')
            ssid = decode_ssid(base64.b64encode(ssid.encode('utf-8')).decode('ascii'))
            connect(ssid)
        elif len(args) == 2 and args[0] == '--check':
            sys.exit(0 if already_connected(decode_ssid(args[1])) else 3)
        elif args == ['--json']:
            data = sys.stdin.buffer.read(4097)
            if len(data) > 4096:
                raise ValueError('Request too large.')
            try:
                payload = json.loads(data)
            except (ValueError, UnicodeError):
                raise ValueError('Invalid request encoding.') from None
            connect_saved(payload)
        elif len(args) == 1 and not args[0].startswith('--'):
            if not sys.stdin.isatty():
                raise RuntimeError('An interactive SSH terminal is required (ssh -t).')
            connect(decode_ssid(args[0]))
        else:
            raise ValueError('Unsupported Wi-Fi command.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, binascii.Error, subprocess.SubprocessError) as error:
        print('BRICQ Wi-Fi: ' + str(error), file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print('\nBRICQ Wi-Fi setup cancelled.', file=sys.stderr)
        sys.exit(130)
