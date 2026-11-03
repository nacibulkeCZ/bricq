"""Behavioral tests for `bricq install-local` — the entry point `bricq push` targets."""
import pytest

import manager


def test_install_local_from_directory(tmp_root, no_lock, fake_system, firmware_tree):
    tree = firmware_tree()

    manager.install_local(str(tree))

    current = manager.current()
    assert current is not None
    assert (current / 'firmware' / 'app.py').read_text() == 'print("hi")\n'
    assert manager.metadata(current)['version'].startswith('local-')


def test_install_local_from_tarball(tmp_root, no_lock, fake_system, firmware_tarball):
    tarball = firmware_tarball()

    manager.install_local(str(tarball))

    current = manager.current()
    assert current is not None
    assert (current / 'firmware' / 'app.py').read_text() == 'print("hi")\n'


def test_install_local_replaces_existing_release(tmp_root, no_lock, fake_system, firmware_tree):
    first = firmware_tree(
        files={'app.py': 'print("v1")\n', 'requirements.txt': ''},
        name='v1',
    )
    second = firmware_tree(
        files={'app.py': 'print("v2")\n', 'requirements.txt': ''},
        name='v2',
    )

    manager.install_local(str(first))
    manager.install_local(str(second))

    current = manager.current()
    assert (current / 'firmware' / 'app.py').read_text() == 'print("v2")\n'
    previous = manager.current('previous')
    assert previous is not None
    assert (previous / 'firmware' / 'app.py').read_text() == 'print("v1")\n'


def test_install_local_rejects_broken_python(tmp_root, no_lock, fake_system, firmware_tree):
    tree = firmware_tree(files={'app.py': 'def oops(\n', 'requirements.txt': ''})

    with pytest.raises(SyntaxError):
        manager.install_local(str(tree))

    assert manager.current() is None


def test_install_local_rolls_back_on_failed_health_check(
    tmp_root, no_lock, fake_system, firmware_tree,
):
    good = firmware_tree(files={'app.py': 'print("good")\n', 'requirements.txt': ''}, name='good')
    manager.install_local(str(good))
    good_version = manager.metadata(manager.current())['version']

    bad = firmware_tree(files={'app.py': 'print("bad")\n', 'requirements.txt': ''}, name='bad')
    fake_system.fail_next_health_check = True

    with pytest.raises(RuntimeError, match='did not become healthy'):
        manager.install_local(str(bad))

    assert manager.metadata(manager.current())['version'] == good_version
