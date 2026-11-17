"""Route-level tests for the stand Flask app, using a FakeServoBus."""
import pytest

import hardware
from modes import stand


@pytest.fixture
def bus():
    return hardware.FakeServoBus()


@pytest.fixture
def client(bus):
    app = stand.create_app(bus)
    return app.test_client()


def test_state_lists_all_four_legs_with_signs(client):
    response = client.get('/state')
    assert response.status_code == 200
    body = response.get_json()
    assert body['pose'] == hardware.STAND_POSE
    by_name = {entry['leg']: entry for entry in body['legs']}
    assert set(by_name) == {'front-left', 'front-right', 'back-left', 'back-right'}
    assert by_name['front-right']['sign'] == 1
    assert by_name['back-right']['sign'] == 1
    assert by_name['front-left']['sign'] == -1
    assert by_name['back-left']['sign'] == -1
    assert by_name['back-left']['knee_channel'] == 9
    assert by_name['back-left']['thigh_channel'] == 11


def test_stand_pose_constant_present_and_in_range(client):
    thigh, knee = hardware.STAND_POSE['thigh'], hardware.STAND_POSE['knee']
    lo, hi = hardware.ANGLE_RANGE
    assert lo <= thigh <= hi
    assert lo <= knee <= hi


def test_leg_signs_cover_every_leg(client):
    assert set(hardware.LEG_SIGNS) == set(hardware.LEGS)


def test_pose_applies_to_all_eight_servos_with_sign_flip(client, bus):
    response = client.post('/pose', json={'thigh': 10, 'knee': -30})

    assert response.status_code == 200
    # Right side — unflipped
    assert bus.positions[0] == 10    # front-right thigh
    assert bus.positions[2] == -30   # front-right knee
    assert bus.positions[4] == 10    # back-right thigh
    assert bus.positions[6] == -30   # back-right knee
    # Left side — flipped
    assert bus.positions[15] == -10  # front-left thigh
    assert bus.positions[13] == 30   # front-left knee
    assert bus.positions[11] == -10  # back-left thigh
    assert bus.positions[9] == 30    # back-left knee


def test_pose_partial_update_preserves_other_axis(client, bus):
    client.post('/pose', json={'thigh': 10, 'knee': -30})
    response = client.post('/pose', json={'knee': -45})

    assert response.status_code == 200
    body = response.get_json()
    assert body['pose'] == {'thigh': 10, 'knee': -45}
    # Right-side back leg confirms both axes applied together on the second call.
    assert bus.positions[4] == 10
    assert bus.positions[6] == -45


def test_pose_rejects_angle_above_range(client, bus):
    response = client.post('/pose', json={'thigh': 100, 'knee': 0})
    assert response.status_code == 400


def test_pose_rejects_angle_below_range(client, bus):
    response = client.post('/pose', json={'thigh': -200, 'knee': 0})
    assert response.status_code == 400


def test_pose_rejects_non_numeric_angle(client, bus):
    response = client.post('/pose', json={'thigh': 'hi', 'knee': 0})
    assert response.status_code == 400


def test_pose_rejects_boolean_angle_disguised_as_number(client, bus):
    response = client.post('/pose', json={'knee': True})
    assert response.status_code == 400


def test_pose_rejects_non_object_payload(client, bus):
    response = client.post('/pose', data='not json',
                           content_type='application/json')
    assert response.status_code == 400


def test_release_frees_every_configured_servo(client, bus):
    client.post('/pose', json={'thigh': 10, 'knee': -30})
    response = client.post('/release')

    assert response.status_code == 200
    for channel in (0, 2, 4, 6, 9, 11, 13, 15):
        assert bus.positions[channel] is None


def test_health_reports_stand_mode(client):
    response = client.get('/health')
    assert response.status_code == 200
    body = response.get_json()
    assert body['mode'] == 'stand'
    assert body['armed'] is True
    assert body['healthy'] is True


def test_index_returns_html(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'<!doctype html>' in response.data.lower() or b'<!DOCTYPE html>' in response.data


def test_shutdown_releases_all_configured_servos(bus):
    app = stand.create_app(bus)
    client = app.test_client()
    client.post('/pose', json={'thigh': 10, 'knee': -30})

    stand.release_all(app)

    for channel in (0, 2, 4, 6, 9, 11, 13, 15):
        assert bus.positions[channel] is None
        assert ('release', channel) in bus.calls
