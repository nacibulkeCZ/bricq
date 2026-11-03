"""Tests for the shared, content-addressed venv cache under ROOT/venvs/."""
import pytest

import manager


def _reqs(path, content):
    path.write_text(content)
    return path


def test_ensure_venv_creates_dir_and_ready_marker(tmp_root, fake_system, tmp_path):
    req = _reqs(tmp_path / 'r.txt', '')

    venv = manager.ensure_venv(req)

    assert venv.exists()
    assert (venv / '.ready').exists()
    assert venv.parent == tmp_root / 'venvs'


def test_ensure_venv_hash_is_stable_for_same_content(tmp_root, fake_system, tmp_path):
    req1 = _reqs(tmp_path / 'a.txt', 'Flask>=3\n')
    req2 = _reqs(tmp_path / 'b.txt', 'Flask>=3\n')

    assert manager.ensure_venv(req1) == manager.ensure_venv(req2)


def test_ensure_venv_ignores_comments_and_blank_lines_when_hashing(
    tmp_root, fake_system, tmp_path,
):
    plain = _reqs(tmp_path / 'plain.txt', 'Flask>=3\n')
    noisy = _reqs(
        tmp_path / 'noisy.txt',
        '\n# comment\nFlask>=3\n   \n# another\n',
    )

    assert manager.ensure_venv(plain) == manager.ensure_venv(noisy)


def test_ensure_venv_different_packages_use_different_venvs(
    tmp_root, fake_system, tmp_path,
):
    a = _reqs(tmp_path / 'a.txt', 'Flask>=3\n')
    b = _reqs(tmp_path / 'b.txt', 'requests\n')

    assert manager.ensure_venv(a) != manager.ensure_venv(b)


def _is_venv_create(call):
    return '-m' in call and 'venv' in call


def _is_pip_install(call):
    return '-m' in call and 'pip' in call and 'install' in call


def test_ensure_venv_skips_rebuild_when_marker_present(
    tmp_root, fake_system, tmp_path,
):
    req = _reqs(tmp_path / 'r.txt', '')
    manager.ensure_venv(req)
    fake_system.run_calls.clear()

    manager.ensure_venv(req)

    assert [c for c in fake_system.run_calls if _is_venv_create(c)] == []


def test_ensure_venv_rebuilds_when_marker_missing(tmp_root, fake_system, tmp_path):
    req = _reqs(tmp_path / 'r.txt', '')
    venv = manager.ensure_venv(req)
    (venv / '.ready').unlink()
    fake_system.run_calls.clear()

    manager.ensure_venv(req)

    assert any(_is_venv_create(c) for c in fake_system.run_calls)


def test_ensure_venv_runs_pip_install_only_when_requirements_have_entries(
    tmp_root, fake_system, tmp_path,
):
    empty = _reqs(tmp_path / 'empty.txt', '# just a comment\n')

    manager.ensure_venv(empty)

    assert [c for c in fake_system.run_calls if _is_pip_install(c)] == []


def test_ensure_venv_runs_pip_install_when_requirements_present(
    tmp_root, fake_system, tmp_path,
):
    req = _reqs(tmp_path / 'r.txt', 'Flask>=3\n')

    manager.ensure_venv(req)

    assert len([c for c in fake_system.run_calls if _is_pip_install(c)]) == 1


def test_prepare_shares_venv_between_releases_with_same_requirements(
    tmp_root, no_lock, fake_system, firmware_tree,
):
    tree_a = firmware_tree(
        files={'app.py': 'print("a")\n', 'requirements.txt': 'Flask>=3\n'},
        name='a',
    )
    tree_b = firmware_tree(
        files={'app.py': 'print("b")\n', 'requirements.txt': 'Flask>=3\n'},
        name='b',
    )

    manager.install_local(str(tree_a))
    fake_system.run_calls.clear()
    manager.install_local(str(tree_b))

    second_run_venv_builds = [c for c in fake_system.run_calls if _is_venv_create(c)]
    second_run_pip_installs = [c for c in fake_system.run_calls if _is_pip_install(c)]
    assert second_run_venv_builds == [], 'cached venv should not be rebuilt'
    assert second_run_pip_installs == [], 'cached venv should skip pip install too'
