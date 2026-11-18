# Recovering sudo access on the Pi (and installing the new manager.py)

The `bricq` account is locked (no password, key-only SSH) and its sudoers policy
only lets it run a few `systemctl` commands. There's no admin account you know
the password for. This guide walks through creating a fresh sudo-capable user
by editing the SD card from Windows, then uses that account once to install
the new manager.py so `bricq <mode>` discovers any script in `firmware/modes/`
with no CLI edits forever.

Do this once. Target time: 15 minutes.

## What you'll need

- The Pi's SD card.
- A card reader for your Windows machine.
- An SSH key pair on your machine (you already have one — it's how you SSH as
  `bricq`). The public key is usually at `C:\Users\stebu\.ssh\id_ed25519.pub`
  or `id_rsa.pub`.
- Your existing `ssh bricq` access (we use it briefly to generate a password
  hash).

## Step 1 — Generate the password hash

Pick a password for a new admin user (e.g. `stebu`). Over SSH to the Pi as
`bricq`:

    ssh bricq 'openssl passwd -6'

It will prompt twice. Copy the full string it prints — it looks like
`$6$abc...$long/base64/stuff`. That's the hash.

## Step 2 — Power down the Pi, pull the SD card

- `ssh bricq 'sudo -n systemctl stop bricq.service; sudo -n shutdown -h now'`
  (if the shutdown command isn't in your sudoers, just unplug the Pi — a
  clean quadruped shutdown doesn't matter here.)
- Wait until the Pi's LEDs go quiet.
- Remove the SD card and plug it into your Windows machine.

Windows mounts the boot partition as a FAT32 drive (usually one of the
rightmost drive letters). The Linux root partition won't be visible without
extra tools — we only touch the boot partition.

## Step 3 — Create `userconf.txt` on the boot partition

In the boot partition's root (the drive Windows just mounted), create a file
called `userconf.txt` (plain text). Put exactly one line in it:

    stebu:$6$abc...$long/base64/stuff

That is: `username:password_hash` — no spaces, no newline at the end other
than what your editor adds automatically. Use the hash you copied in Step 1.
Replace `stebu` with whatever username you want for the admin account.

Pi OS Bookworm reads this on next boot and creates the user with that hashed
password, adds them to the `sudo` group, then deletes the file.

**Where exactly does the file go?** On recent Pi OS the boot partition in the
device shows up on Windows as a FAT32 drive with files like `config.txt`,
`cmdline.txt`, `bcm*.dtb`. Put `userconf.txt` right next to those, at the
root of that drive. (On the Pi itself after boot that path is
`/boot/firmware/userconf.txt`.)

## Step 4 — Authorize your SSH key for the new user

Still on the SD card, we'd love to drop your `authorized_keys` here too, but
the Linux home directory lives on a partition Windows can't easily read. So
we'll do it from the Pi after Step 5.

## Step 5 — Reinsert, boot, SSH in

- Put the SD card back in the Pi, power on.
- Wait ~30s for first boot.
- From Windows:

      ssh stebu@bricq.local

- At the password prompt, type the password you chose in Step 1.
- If `bricq.local` doesn't resolve for this new user (mDNS can be flaky), try
  the USB address: `ssh stebu@10.12.194.1`.

## Step 6 — Install your SSH key for this user (password-less future logins)

Still in the `stebu` SSH session on the Pi:

    mkdir -p ~/.ssh && chmod 700 ~/.ssh

Then from your Windows machine in a **new** PowerShell window:

    type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh stebu@bricq.local "cat >> ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys"

(Use `id_rsa.pub` instead if your key is RSA.) After this, `ssh stebu@bricq.local`
works without a password.

## Step 7 — Install the new manager.py

This is the one-time act that unlocks discovery-based mode dispatch. On the Pi
as `stebu`:

    sudo install -m 644 /home/bricq/.local/share/bricq/current/firmware/manager.py /usr/local/lib/bricq/manager.py

Enter your password when prompted. Verify:

    bricq stand --help 2>&1 | head -2
    # Should NOT say "invalid choice: 'stand'" any more.

Actually, better verification — ask bricq to list modes by giving it a bad
name:

    bricq nonsense
    # Should print: "Unknown command or mode: nonsense. Available modes: calibrate, legtest, stand, walktest"

If you see that, discovery is live. From now on, adding a new file to
`firmware/modes/` and running `bricq update` makes `bricq <new-name>` work
with zero CLI changes.

## Step 8 — Verify everything still works

    bricq status
    bricq stand   # Ctrl+C to exit
    bricq walktest
    bricq calibrate

## Cleanup / notes

- The `stebu` user is now a durable sudo account. Keep its password
  somewhere you'll find next time (password manager).
- Never put plaintext passwords in `userconf.txt` — always hashes.
- If you want to delete the `userconf.txt` file manually later it's fine, but
  Pi OS auto-removes it after first-boot provisioning.
- Future manager.py changes will need Step 7 re-run. Scope of this problem is
  now small — modes don't need it.

## If something goes wrong

- **Can't find the boot drive on Windows**: unplug/replug the card, check Disk
  Management. Linux root partition shows as "not formatted" — don't let Windows
  reformat it.
- **SSH prompts for password endlessly**: the hash in `userconf.txt` was
  malformed. Regenerate it in Step 1 verbatim.
- **`sudo install` says not in sudoers**: the Bookworm first-boot provisioner
  didn't run. Check the file is named exactly `userconf.txt` (not
  `userconf.txt.txt` — Windows loves that trick) and the content is one line
  `user:hash`.
- **Robot still live but you're locked out**: you can always just reflash the
  SD card and `ssh bricq` from the old key, no data loss in the firmware
  release tree because releases live under `~bricq/.local/share/bricq/`.
