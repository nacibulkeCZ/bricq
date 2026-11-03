"""Tests for the hardware abstraction (ServoBus, LEGS, resolve_leg)."""
import pytest

import hardware


def test_fake_servo_bus_records_set_and_release():
    bus = hardware.FakeServoBus()

    bus.set_angle(0, 15)
    bus.set_angle(2, -30)
    bus.release(0)

    assert bus.positions == {0: 15, 2: -30, 0: None} or bus.positions == {0: None, 2: -30}
    assert ('set', 0, 15) in bus.calls
    assert ('set', 2, -30) in bus.calls
    assert ('release', 0) in bus.calls


def test_fake_servo_bus_tracks_latest_position():
    bus = hardware.FakeServoBus()
    bus.set_angle(0, 15)
    bus.set_angle(0, 45)

    assert bus.positions[0] == 45


def test_legs_defines_all_four_quadruped_legs():
    assert set(hardware.LEGS) == {'front-left', 'front-right', 'back-left', 'back-right'}


def test_front_right_is_wired_to_known_channels():
    assert hardware.LEGS['front-right'] == {'knee': 0, 'thigh': 2}


def test_other_legs_are_placeholders_until_wired():
    for name in ('front-left', 'back-left', 'back-right'):
        channels = hardware.LEGS[name]
        assert set(channels) == {'knee', 'thigh'}
        assert all(ch is None for ch in channels.values()), (
            f'{name} appears to be wired; update test if that is intentional'
        )


def test_resolve_leg_returns_channel_map_for_wired_leg():
    assert hardware.resolve_leg('front-right') == {'knee': 0, 'thigh': 2}


def test_resolve_leg_rejects_unknown_name():
    with pytest.raises(ValueError, match='Unknown leg'):
        hardware.resolve_leg('center-middle')


def test_resolve_leg_rejects_unwired_leg():
    with pytest.raises(ValueError, match='not wired'):
        hardware.resolve_leg('front-left')


def test_default_bus_returns_fake_when_adafruit_unavailable(monkeypatch):
    monkeypatch.setattr(hardware, 'AdafruitServoBus', None)
    bus = hardware.default_bus()
    assert isinstance(bus, hardware.FakeServoBus)


def test_angle_range_is_signed_degrees():
    assert hardware.ANGLE_RANGE == (-90, 90)


def test_pulse_width_range_matches_reference_servos():
    assert hardware.PULSE_WIDTH_RANGE == (500, 2500)
