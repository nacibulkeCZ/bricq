"""Copy top-level Pi Python scripts into an archive without executing them."""
from pathlib import Path
import re
import sys
import tarfile


def create_backup(home, name):
    if not re.fullmatch(r'bricq-tests-[0-9]{8}-[0-9]{6}\.tar\.gz', name):
        raise ValueError('Unexpected backup filename.')
    files = sorted(p for p in home.glob('*.py') if p.is_file() and not p.is_symlink())
    if not files:
        raise RuntimeError('No top-level Python scripts found; inspect their location.')
    destination = home / name
    with tarfile.open(destination, 'x:gz') as archive:
        for path in files:
            archive.add(path, arcname=path.name, recursive=False)
    print('Backed up:', ', '.join(p.name for p in files))
    return destination


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: backup-tests.py BACKUP_FILENAME')
    create_backup(Path.home(), sys.argv[1])
