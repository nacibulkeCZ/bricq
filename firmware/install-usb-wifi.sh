#!/bin/bash
set -euo pipefail
test "$(id -u)" -eq 0 || { echo 'Run this installer with sudo.'; exit 1; }
src=$(cd -- "$(dirname -- "$0")" && pwd)
id bricq >/dev/null
test -d /usr/local/lib/bricq
test -x /usr/bin/nmcli
test -d /sys/class/net/usb0
systemctl is-active --quiet NetworkManager
sh -n "$src/bricq"
python3 -c 'import ast,sys; ast.parse(open(sys.argv[1], encoding="utf-8").read())' "$src/usb-wifi.py"
policy=$(mktemp)
trap 'rm -f "$policy"' EXIT
# The root-owned helper accepts one validated SSID and only operates wlan0.
# It cannot execute arbitrary commands or edit the USB profiles.
printf 'bricq ALL=(root) NOPASSWD: /usr/local/sbin/bricq-wifi *\n' > "$policy"
visudo -cf "$policy"
stamp=$(date +%Y%m%d-%H%M%S)
for file in /usr/local/lib/bricq/usb-wifi.py /usr/local/sbin/bricq-wifi /etc/sudoers.d/bricq-wifi /usr/local/bin/bricq; do
    if [ -e "$file" ]; then cp -p -- "$file" "$file.backup-$stamp"; fi
done
install -o root -g root -m 644 "$src/usb-wifi.py" /usr/local/lib/bricq/usb-wifi.py
install -o root -g root -m 755 "$src/bricq-wifi" /usr/local/sbin/bricq-wifi
install -o root -g root -m 440 "$policy" /etc/sudoers.d/bricq-wifi
install -o root -g root -m 755 "$src/bricq" /usr/local/bin/bricq
echo 'BRICQ USB Wi-Fi helper installed. No reboot or Wi-Fi change was performed.'
