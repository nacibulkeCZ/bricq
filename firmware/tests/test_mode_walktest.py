"""Route-level tests for the walktest Flask app, using a FakeServoBus."""
import math

import pytest

import hardware
from modes import walktest


@pytest.fixture
def bus():
    return hardware.FakeServoBus()


@pytest.fixture
def client(bus):
    app = walktest.create_app(bus)
    return app.test_client()


def test_startup_applies_stand_pose_to_every_leg(bus):
    walktest.create_app(bus)
    # Right side: unflipped stand pose.
    assert bus.positions[0] == hardware.STAND_POSE['thigh']
    assert bus.positions[2] == hardware.STAND_POSE['knee']
    assert bus.positions[4] == hardware.STAND_POSE['thigh']
    assert bus.positions[6] == hardware.STAND_POSE['knee']
    # Left side: sign-flipped stand pose.
    assert bus.positions[15] == -hardware.STAND_POSE['thigh']
    assert bus.positions[13] == -hardware.STAND_POSE['knee']
    assert bus.positions[11] == -hardware.STAND_POSE['thigh']
    assert bus.positions[9] == -hardware.STAND_POSE['knee']


def test_state_reports_trot_phasing(client):
    body = client.get('/state').get_json()
    offsets = {entry['leg']: entry['offset_deg'] for entry in body['legs']}
    assert offsets['front-left'] == 0
    assert offsets['back-right'] == 0
    assert offsets['front-right'] == 180
    assert offsets['back-left'] == 180


def test_state_reports_stand_pose_constants(client):
    body = client.get('/state').get_json()
    assert body['stand_pose'] == hardware.STAND_POSE


def test_diagonal_pair_shares_phase_and_opposite_pair_is_mirrored():
    stride = 20
    for phase in (0.0, math.pi / 3, math.pi, 1.7 * math.pi):
        fl_thigh, fl_knee = walktest.leg_angles('front-left', phase, stride)
        br_thigh, br_knee = walktest.leg_angles('back-right', phase, stride)
        fr_thigh, fr_knee = walktest.leg_angles('front-right', phase, stride)
        bl_thigh, bl_knee = walktest.leg_angles('back-left', phase, stride)
        # Front-left (sign=-1) and back-right (sign=+1) share gait phase
        # but are sign-flipped — the mirrored servo convention cancels the
        # body-frame "same motion" into opposite servo commands.
        assert fl_thigh == -br_thigh
        assert fl_knee == -br_knee
        # Front-right and back-left are the other diagonal pair.
        assert fr_thigh == -bl_thigh
        assert fr_knee == -bl_knee


def test_knee_never_dips_below_stand_pose():
    # max(0, cos) → knee only lifts (positive delta), never drops.
    for phase in [i * math.pi / 8 for i in range(16)]:
        _, knee = walktest.leg_angles('front-right', phase, stride=20)
        assert knee >= hardware.STAND_POSE['knee']


def test_leg_angles_are_clamped_to_servo_range():
    # Extreme stride would push knee past 90°; clamp protects the servo.
    _, knee = walktest.leg_angles('front-right', phase=0.0, stride=1000)
    lo, hi = hardware.ANGLE_RANGE
    assert lo <= knee <= hi


def test_walk_start_launches_walker_and_state_reflects_running(client):
    response = client.post('/walk/start', json={'stride': 10})
    assert response.status_code == 200
    body = response.get_json()
    assert body['walking'] is True
    client.post('/walk/stop')


def test_walk_stop_returns_to_stand_pose(client, bus):
    client.post('/walk/start', json={'stride': 10})
    response = client.post('/walk/stop')
    assert response.status_code == 200
    assert response.get_json()['walking'] is False
    # After stopping, the right-side stand pose is back.
    assert bus.positions[0] == hardware.STAND_POSE['thigh']
    assert bus.positions[2] == hardware.STAND_POSE['knee']


def test_stand_endpoint_rejects_during_walk(client):
    client.post('/walk/start', json={'stride': 10})
    response = client.post('/stand')
    assert response.status_code == 400
    client.post('/walk/stop')


def test_stride_change_outside_range_rejected(client):
    response = client.post('/walk/stride', json={'stride': 100})
    assert response.status_code == 400


def test_stride_change_inside_range_updates_state(client):
    response = client.post('/walk/stride', json={'stride': 20})
    assert response.status_code == 200
    assert response.get_json()['stride'] == 20


def test_release_stops_walker_and_frees_every_channel(client, bus):
    client.post('/walk/start', json={'stride': 10})
    response = client.post('/release')
    assert response.status_code == 200
    assert response.get_json()['walking'] is False
    for channel in (0, 2, 4, 6, 9, 11, 13, 15):
        assert bus.positions[channel] is None


def test_health_reports_walktest_mode(client):
    body = client.get('/health').get_json()
    assert body['mode'] == 'walktest'
    assert body['armed'] is True


def test_index_returns_html(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'<!doctype html>' in response.data.lower() or b'<!DOCTYPE html>' in response.data


def test_shutdown_releases_all(bus):
    app = walktest.create_app(bus)
    walktest.release_all(app)
    for channel in (0, 2, 4, 6, 9, 11, 13, 15):
        assert bus.positions[channel] is None
