"""Shared fixtures for firmware tests.

Design: `manager.py` is already factored around module-level thin wrappers
(`run`, `control`, `health`, `locked`, `wait_healthy`). Tests monkeypatch those
seams rather than refactoring the module. Add a new fake fixture here when you
add a new seam (e.g. `fake_gpio` once hardware control lands)."""
import contextlib
import io
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import manager  # noqa: E402


@pytest.fixture
def tmp_root(tmp_path, monkeypatch):
    """Redirect `manager.ROOT` and swap the symlink-based pointer for a text file.

    Why: Windows non-admin accounts can't create symlinks (WinError 1314). On the
    Pi the real symlink mechanism runs — this shim preserves the same semantics
    (atomic swap, resolve to target) so orchestration tests can run on Windows."""
    root = tmp_path / 'bricq'
    root.mkdir()
    monkeypatch.setattr(manager, 'ROOT', root)

    def fake_point(name, target):
        temp = root / (name + '.next')
        temp.write_text(str(Path(target).resolve()))
        temp.replace(root / name)

    def fake_current(name='current'):
        pointer = root / name
        if not pointer.exists():
            return None
        return Path(pointer.read_text())

    monkeypatch.setattr(manager, 'point', fake_point)
    monkeypatch.setattr(manager, 'current', fake_current)
    return root


@pytest.fixture
def no_lock(monkeypatch):
    @contextlib.contextmanager
    def noop():
        yield
    monkeypatch.setattr(manager, 'locked', noop)


@pytest.fixture
def fake_system(monkeypatch):
    """One fake covering every system seam `activate()` touches.

    Defaults produce a healthy service and successful activation. Tests mutate
    `recorder` attributes to simulate failures (e.g. set `fail_health=True` to
    exercise the rollback path)."""
    recorder = SimpleNamespace(
        run_calls=[],
        control_calls=[],
        active_state='active',
        fail_next_health_check=False,
    )

    def fake_run(*args, capture=False, timeout=900):
        recorder.run_calls.append(args)
        if 'show' in args and 'ActiveState' in args:
            return recorder.active_state
        if args and args[0] == 'hostname':
            return '192.168.1.42\n'
        return ''

    def fake_control(*args):
        recorder.control_calls.append(args)

    def fake_subprocess_run(cmd, **kw):
        recorder.run_calls.append(('subprocess.run', tuple(cmd)))
        text = ' '.join(str(c) for c in cmd)
        if 'is-failed' in text:
            return SimpleNamespace(returncode=1)
        if 'is-active' in text:
            return SimpleNamespace(returncode=0)
        if 'is-enabled' in text:
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0, stdout='')

    def fake_health():
        cur = manager.current()
        version = manager.metadata(cur)['version'] if cur else 'unknown'
        return {
            'healthy': True,
            'armed': False,
            'mode': 'status-only',
            'version': version,
        }

    def fake_wait_healthy(version):
        if recorder.fail_next_health_check:
            recorder.fail_next_health_check = False
            return False
        return True

    def fake_active():
        return True

    monkeypatch.setattr(manager, 'run', fake_run)
    monkeypatch.setattr(manager, 'control', fake_control)
    monkeypatch.setattr(manager, 'health', fake_health)
    monkeypatch.setattr(manager, 'wait_healthy', fake_wait_healthy)
    monkeypatch.setattr(manager, 'active', fake_active)
    monkeypatch.setattr(manager.subprocess, 'run', fake_subprocess_run)
    return recorder


@pytest.fixture
def firmware_tarball(tmp_path):
    def _make(files=None, name='push.tar.gz'):
        if files is None:
            files = {'app.py': 'print("hi")\n', 'requirements.txt': ''}
        path = tmp_path / name
        with tarfile.open(path, 'w:gz') as tar:
            for rel, content in files.items():
                data = content.encode() if isinstance(content, str) else content
                info = tarfile.TarInfo('firmware/' + rel)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return path
    return _make


@pytest.fixture
def firmware_tree(tmp_path):
    def _make(files=None, name='tree'):
        if files is None:
            files = {'app.py': 'print("hi")\n', 'requirements.txt': ''}
        folder = tmp_path / name
        folder.mkdir()
        for rel, content in files.items():
            dest = folder / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                dest.write_text(content)
            else:
                dest.write_bytes(content)
        return folder
    return _make
