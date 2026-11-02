#!/bin/bash
# Run once through the existing administrator account. Never starts servo tests.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo 'Run with sudo bash install.sh PUBLIC_KEY_FILE'; exit 1; fi
src=$(cd -- "$(dirname -- "$0")" && pwd)
key=${1:?Supply the new computer public key file}
ssh-keygen -l -f "$key" >/dev/null
command -v systemctl >/dev/null
command -v sudo >/dev/null
command -v git >/dev/null || { echo 'Install git first: sudo apt install git'; exit 1; }
python3 -c 'import venv, ensurepip' || { echo 'Install python3-venv first: sudo apt install python3-venv'; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3, 9), "Python 3.9+ required"'
if id bricq >/dev/null 2>&1; then
    if [ "${2:-}" != --resume ]; then
        echo 'Account bricq already exists. An incomplete installation requires explicit --resume.'
        exit 1
    fi
    test "$(getent passwd bricq | cut -d: -f6)" = /home/bricq
    test "$(id -u bricq)" -ne 0
    test -f /usr/local/lib/bricq/manager.py
    test -f /etc/sudoers.d/bricq
    cmp "$src/bricq" /usr/local/bin/bricq
    for unit in bricq.service bricq-watch.service bricq-watch.timer; do
        cmp "$src/$unit" "/etc/systemd/system/$unit"
    done
    grep -Fqx "$(cat "$key")" /home/bricq/.ssh/authorized_keys
    if [ -e /home/bricq/.local/share/bricq/current ] || [ -L /home/bricq/.local/share/bricq/current ]; then
        echo 'A current release exists. Refusing to treat an installed robot as an incomplete setup.'
        exit 1
    fi
    if systemctl is-active --quiet bricq.service; then
        echo 'BRICQ is already running. Refusing installation recovery.'
        exit 1
    fi
    cp -p /usr/local/lib/bricq/manager.py "/usr/local/lib/bricq/manager.py.before-resume.$(date +%s)"
    echo 'Resuming verified incomplete installation; keeping account and authorized keys.'
else
    test ! -e /usr/local/bin/bricq || { echo 'BRICQ is already installed.'; exit 1; }
    test ! -e /etc/sudoers.d/bricq || { echo 'Existing BRICQ sudoers policy; inspect first.'; exit 1; }
    useradd --create-home --shell /bin/bash --comment 'BRICQ robot' bricq
    # Keep a locked password; access is through the supplied per-computer SSH key.
    install -d -m 700 -o bricq -g bricq /home/bricq/.ssh
    install -m 600 -o bricq -g bricq "$key" /home/bricq/.ssh/authorized_keys
    printf '\n. /usr/local/lib/bricq/login.sh\n' >> /home/bricq/.profile
    chown bricq:bricq /home/bricq/.profile
fi
install -d -m 755 /usr/local/lib/bricq
install -m 644 "$src/manager.py" /usr/local/lib/bricq/manager.py
install -m 755 "$src/bricq" /usr/local/bin/bricq
install -m 644 "$src/login.sh" /usr/local/lib/bricq/login.sh
for unit in bricq.service bricq-watch.service bricq-watch.timer; do
    install -m 644 "$src/$unit" "/etc/systemd/system/$unit"
done
# No unrestricted sudo and no wildcard command arguments.
systemctl_path=$(command -v systemctl)
policy=$(mktemp)
trap 'rm -f "$policy"' EXIT
printf 'bricq ALL=(root) NOPASSWD: %s restart bricq.service, %s stop bricq.service, %s reset-failed bricq.service, %s enable --now bricq-watch.timer, %s disable --now bricq-watch.timer, %s -u bricq.service -n 80 --no-pager\n' "$systemctl_path" "$systemctl_path" "$systemctl_path" "$systemctl_path" "$systemctl_path" "$(command -v journalctl)" > "$policy"
visudo -cf "$policy"
install -m 440 "$policy" /etc/sudoers.d/bricq
systemctl daemon-reload
stage=$(mktemp -d /tmp/bricq-install.XXXXXXXX)
chmod 755 "$stage"
cp -R "$src/." "$stage/"
chown -R bricq:bricq "$stage"
runuser -u bricq -- env HOME=/home/bricq /usr/local/bin/bricq install-local "$stage"
rm -rf -- "$stage"
systemctl enable bricq.service
echo 'Installed. Existing user, servo_panel.py and servo-env were not modified.'
echo 'On Windows, verify: ssh bricq'
echo 'Automatic updates remain OFF. Push firmware to GitHub before bricq update.'
