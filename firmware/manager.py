"""Stable management layer; installed separately from downloaded application code."""
import argparse
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path.home() / '.local/share/bricq'
REPO = 'https://github.com/nacibulkeCZ/bricg.git'
BRANCH = 'main'
SYSTEMCTL = shutil.which('systemctl') or '/usr/bin/systemctl'


def run(*args, capture=False, timeout=900):
    return subprocess.run(args, check=True, timeout=timeout,
                          stdout=subprocess.PIPE if capture else None,
                          text=True).stdout


def control(*args):
    run('sudo', '-n', SYSTEMCTL, *args)


def reset_failed():
    # An inactive first-install unit may be unloaded: nothing to reset.
    result = subprocess.run([SYSTEMCTL, 'is-failed', '--quiet', 'bricq.service'])
    if result.returncode == 0:
        control('reset-failed', 'bricq.service')


def health():
    # Ignore proxy environment settings for the local health endpoint.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://127.0.0.1:8765/health', timeout=2) as response:
        return json.load(response)


def active():
    return subprocess.run([SYSTEMCTL, 'is-active', '--quiet', 'bricq.service']).returncode == 0


def ensure_idle():
    state = run(SYSTEMCTL, 'show', '-p', 'ActiveState', '--value', 'bricq.service', capture=True).strip()
    if state == 'inactive':
        return
    if state != 'active':
        raise RuntimeError('Service state is uncertain; inspect bricq status/logs before updating.')
    result = health()
    # This first implementation deliberately refuses updates to any future motion mode.
    if result.get('healthy') is not True or result.get('armed') is not False or result.get('mode') != 'status-only':
        raise RuntimeError('Update deferred: robot is not confirmed idle in status-only mode.')


def current(name='current'):
    link = ROOT / name
    return link.resolve() if link.is_symlink() else None


def point(name, target):
    temp = ROOT / (name + '.next')
    temp.unlink(missing_ok=True)
    temp.symlink_to(target, target_is_directory=True)
    temp.replace(ROOT / name)


@contextlib.contextmanager
def locked():
    import fcntl
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / 'update.lock').open('w') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another update or rollback is already running.')
        yield


def validate(folder):
    if not (folder / 'app.py').is_file() or not (folder / 'requirements.txt').is_file():
        raise RuntimeError('Release must contain app.py and requirements.txt.')
    for path in folder.rglob('*.py'):
        ast.parse(path.read_bytes(), filename=str(path))


def extract_firmware(data, target):
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive.getmembers():
            parts = Path(member.name).parts
            if not parts or parts[0] != 'firmware' or '..' in parts or Path(member.name).is_absolute():
                raise RuntimeError('Unexpected archive path.')
            if member.isdir():
                continue
            if not member.isfile():
                raise RuntimeError('Links and special files are not allowed in firmware.')
            dest = target.joinpath(*parts[1:])
            dest.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, dest.open('wb') as out:
                shutil.copyfileobj(source, out)


def wait_healthy(version):
    for _ in range(30):
        try:
            result = health()
            if active() and result.get('healthy') is True and result.get('version') == version:
                return True
        except (OSError, ValueError):
            pass
        time.sleep(1)
    return False


def metadata(release):
    return json.loads((release / 'version.json').read_text())


def activate(release):
    ensure_idle()
    old = current()
    control('stop', 'bricq.service')
    point('current', release)
    try:
        reset_failed()
        control('restart', 'bricq.service')
        if not wait_healthy(metadata(release)['version']):
            raise RuntimeError('New release did not become healthy within 30 seconds.')
    except Exception:
        control('stop', 'bricq.service')
        if old:
            point('current', old)
            reset_failed()
            control('restart', 'bricq.service')
            if not wait_healthy(metadata(old)['version']):
                raise RuntimeError('Update and recovery failed. Inspect bricq logs; files retained.')
            print('Restored previous healthy release.', file=sys.stderr)
        else:
            (ROOT / 'current').unlink(missing_ok=True)
        raise
    if old and old != release:
        point('previous', old)
    print('BRICQ running:', metadata(release)['version'])


def _requirements_entries(requirements_file):
    return [
        line.strip() for line in requirements_file.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    ]


def ensure_venv(requirements_file):
    """Return path to a ready, content-addressed venv matching this requirements file.

    Reuses the venv across releases when requirements.txt is unchanged, so
    `bricq push` doesn't pay the pip-install cost on every iteration. Interrupted
    installs are detected via a missing `.ready` marker and get rebuilt."""
    entries = _requirements_entries(requirements_file)
    digest = hashlib.sha256('\n'.join(sorted(entries)).encode()).hexdigest()[:16]
    venv_root = ROOT / 'venvs' / digest
    marker = venv_root / '.ready'
    if marker.exists():
        return venv_root
    if venv_root.exists():
        shutil.rmtree(venv_root)
    venv_root.parent.mkdir(parents=True, exist_ok=True)
    venv_root.mkdir()
    run(sys.executable, '-m', 'venv', str(venv_root))
    if entries:
        run(str(venv_root / 'bin/python'), '-m', 'pip', 'install', '-r', str(requirements_file), timeout=1500)
    marker.write_text('\n'.join(sorted(entries)) + '\n')
    return venv_root


def _link_venv(release_dir, venv_dir):
    (release_dir / 'venv').symlink_to(venv_dir, target_is_directory=True)


def prepare(source, version, tree):
    validate(source)
    releases = ROOT / 'releases'
    releases.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='release-', dir=releases))
    try:
        shutil.copytree(source, stage / 'firmware')
        venv_dir = ensure_venv(stage / 'firmware' / 'requirements.txt')
        _link_venv(stage, venv_dir)
        (stage / 'version.json').write_text(json.dumps({'version': version, 'tree': tree}) + '\n')
        return stage
    except Exception:
        shutil.rmtree(stage)
        raise


def update():
    with locked():
        ensure_idle()
        source = ROOT / 'source.git'
        if not source.exists():
            run('git', 'init', '--bare', str(source))
        run('git', '-C', str(source), 'fetch', '--depth=1', REPO, 'refs/heads/' + BRANCH)
        commit = run('git', '-C', str(source), 'rev-parse', 'FETCH_HEAD', capture=True).strip()
        tree = run('git', '-C', str(source), 'rev-parse', commit + ':firmware', capture=True).strip()
        old = current()
        if old and metadata(old)['tree'] == tree:
            print('Firmware is already up to date.')
            return
        data = subprocess.check_output(['git', '-C', str(source), 'archive', commit, 'firmware'], timeout=60)
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            extract_firmware(data, Path(folder))
            release = prepare(Path(folder), commit, tree)
        activate(release)
        print('Application updated. Installer, management commands and system services are maintained separately.')


def install_local(path):
    with locked():
        source_arg = Path(path).resolve()
        if source_arg.is_file():
            data = source_arg.read_bytes()
            with tempfile.TemporaryDirectory(dir=ROOT) as workspace:
                source = Path(workspace)
                extract_firmware(data, source)
                _install_tree(source)
        else:
            _install_tree(source_arg)


def _install_tree(source):
    validate(source)
    digest = hashlib.sha256()
    for path in sorted(source.rglob('*')):
        if path.is_file():
            digest.update(str(path.relative_to(source)).encode())
            digest.update(path.read_bytes())
    version = 'local-' + digest.hexdigest()[:12]
    activate(prepare(source, version, version))


def status():
    release = current()
    print('Version:', metadata(release)['version'] if release else 'not installed')
    print('Service:', 'running' if active() else 'not running')
    print('Addresses:', run('hostname', '-I', capture=True).strip())
    if shutil.which('iwgetid'):
        result = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True)
        print('Wi-Fi:', result.stdout.strip() or 'not connected')
    enabled = subprocess.run([SYSTEMCTL, 'is-enabled', '--quiet', 'bricq-watch.timer']).returncode == 0
    print('Auto updates:', 'enabled' if enabled else 'disabled')
    try:
        print('Application:', json.dumps(health()))
    except (OSError, ValueError):
        print('Application health: unavailable')


def serve():
    release = current()
    if not release:
        raise RuntimeError('No installed release.')
    env = dict(os.environ, BRICQ_VERSION=metadata(release)['version'])
    python = str(release / 'venv/bin/python')
    os.execve(python, [python, '-u', str(release / 'firmware/app.py')], env)


def run_mode(mode_name, mode_arg):
    release = current()
    if not release:
        raise RuntimeError('No installed release. Install firmware first.')
    was_active = active()
    if was_active:
        control('stop', 'bricq.service')
    try:
        python = str(release / 'venv/bin/python')
        script = release / 'firmware' / 'modes' / (mode_name + '.py')
        completed = subprocess.run([python, '-u', str(script), mode_arg])
        if completed.returncode != 0:
            raise RuntimeError('%s exited with code %d' % (mode_name, completed.returncode))
    finally:
        if was_active:
            reset_failed()
            control('restart', 'bricq.service')


def main_with_args(argv):
    parser = argparse.ArgumentParser(description='BRICQ robot console')
    parser.add_argument('command', choices=['status', 'update', 'rollback', 'watch', 'logs', 'serve', 'install-local', 'legtest'])
    parser.add_argument('argument', nargs='?')
    args = parser.parse_args(argv)
    if args.command == 'status':
        status()
    elif args.command == 'update':
        update()
    elif args.command == 'rollback':
        with locked():
            previous = current('previous')
            if not previous:
                raise RuntimeError('No previous release exists.')
            activate(previous)
    elif args.command == 'watch':
        if args.argument not in (None, 'start', 'stop'):
            parser.error('Use bricq watch [start|stop].')
        control('disable' if args.argument == 'stop' else 'enable', '--now', 'bricq-watch.timer')
    elif args.command == 'logs':
        # --user-unit is not applicable: this is a system unit running as bricq.
        run('sudo', '-n', shutil.which('journalctl') or '/usr/bin/journalctl', '-u', 'bricq.service', '-n', '80', '--no-pager')
    elif args.command == 'serve':
        serve()
    elif args.command == 'legtest':
        if not args.argument:
            parser.error('legtest requires a leg name. Available: front-left, front-right, back-left, back-right')
        run_mode('legtest', args.argument)
    else:
        if not args.argument:
            parser.error('install-local requires a firmware directory.')
        install_local(args.argument)


def main():
    main_with_args(sys.argv[1:])


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, SyntaxError, subprocess.SubprocessError) as error:
        print('BRICQ:', error, file=sys.stderr)
        sys.exit(1)
