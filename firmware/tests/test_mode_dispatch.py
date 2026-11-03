"""Tests for the mode dispatch in manager.run_mode:
stop status app → exec mode script → always restart status app on exit."""
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import manager


@pytest.fixture
def installed_release(tmp_root, monkeypatch):
    release = tmp_root / 'releases' / 'release-test'
    (release / 'firmware' / 'modes').mkdir(parents=True)
    (release / 'venv' / 'bin').mkdir(parents=True)
    (release / 'venv' / 'bin' / 'python').write_text('#!/usr/bin/env python3\n')
    monkeypatch.setattr(manager, 'current', lambda name='current': release if name == 'current' else None)
    return release


@pytest.fixture
def mode_runner(monkeypatch):
    """Replace subprocess.run so we can observe how run_mode launches the mode."""
    recorder = SimpleNamespace(invocations=[], return_code=0)

    def fake_run(cmd, **kw):
        recorder.invocations.append(tuple(cmd))
        return SimpleNamespace(returncode=recorder.return_code, stdout='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    return recorder


def test_run_mode_invokes_release_venv_python_with_mode_script_and_arg(
    installed_release, fake_system, mode_runner, monkeypatch,
):
    monkeypatch.setattr(manager, 'active', lambda: False)

    manager.run_mode('legtest', 'front-right')

    assert any(
        str(installed_release / 'venv' / 'bin' / 'python') in cmd
        and str(installed_release / 'firmware' / 'modes' / 'legtest.py') in cmd
        and 'front-right' in cmd
        for cmd in mode_runner.invocations
    )


def test_run_mode_stops_status_service_before_mode_and_restarts_after(
    installed_release, fake_system, mode_runner, monkeypatch,
):
    monkeypatch.setattr(manager, 'active', lambda: True)

    manager.run_mode('legtest', 'front-right')

    actions = [args[0] for args in fake_system.control_calls]
    assert actions.index('stop') < actions.index('restart')


def test_run_mode_restarts_status_service_even_if_mode_crashes(
    installed_release, fake_system, mode_runner, monkeypatch,
):
    monkeypatch.setattr(manager, 'active', lambda: True)
    mode_runner.return_code = 1

    with pytest.raises(RuntimeError, match='legtest exited'):
        manager.run_mode('legtest', 'front-right')

    assert ('restart', 'bricq.service') in fake_system.control_calls


def test_run_mode_does_not_touch_status_service_if_it_was_not_active(
    installed_release, fake_system, mode_runner, monkeypatch,
):
    monkeypatch.setattr(manager, 'active', lambda: False)

    manager.run_mode('legtest', 'front-right')

    actions = [args[0] for args in fake_system.control_calls]
    assert 'stop' not in actions
    assert 'restart' not in actions


def test_run_mode_errors_without_installed_release(fake_system, monkeypatch, tmp_root):
    monkeypatch.setattr(manager, 'current', lambda name='current': None)
    with pytest.raises(RuntimeError, match='No installed release'):
        manager.run_mode('legtest', 'front-right')


def test_legtest_cli_requires_leg_name():
    with pytest.raises(SystemExit):
        manager.main_with_args(['legtest'])


def test_legtest_cli_dispatches_to_run_mode(monkeypatch):
    called = []
    monkeypatch.setattr(manager, 'run_mode', lambda name, arg: called.append((name, arg)))
    manager.main_with_args(['legtest', 'front-right'])
    assert called == [('legtest', 'front-right')]
