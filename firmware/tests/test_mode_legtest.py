"""Route-level tests for the legtest Flask app, using a FakeServoBus."""
import pytest

import hardware
from modes import legtest


@pytest.fixture
def bus():
    return hardware.FakeServoBus()


@pytest.fixture
def client(bus):
    app = legtest.create_app('front-right', bus)
    return app.test_client()


def test_create_app_rejects_unknown_leg(bus):
    with pytest.raises(ValueError, match='Unknown leg'):
        legtest.create_app('center-middle', bus)


def test_create_app_rejects_unwired_leg(bus):
    with pytest.raises(ValueError, match='not wired'):
        legtest.create_app('front-left', bus)


def test_state_lists_servos_for_configured_leg(client):
    response = client.get('/state')
    assert response.status_code == 200
    body = response.get_json()
    assert body['leg'] == 'front-right'
    channels = {entry['channel']: entry for entry in body['servos']}
    assert set(channels) == {0, 2}
    assert channels[0]['angle'] is None
    assert channels[2]['angle'] is None


def test_move_sets_servo_angle_and_returns_updated_state(client, bus):
    response = client.post('/move', json={'channel': 0, 'angle': 15})

    assert response.status_code == 200
    assert bus.positions[0] == 15
    body = response.get_json()
    channel_zero = next(s for s in body['servos'] if s['channel'] == 0)
    assert channel_zero['angle'] == 15


def test_move_rejects_angle_above_range(client, bus):
    response = client.post('/move', json={'channel': 0, 'angle': 100})
    assert response.status_code == 400
    assert 0 not in bus.positions


def test_move_rejects_angle_below_range(client, bus):
    response = client.post('/move', json={'channel': 0, 'angle': -200})
    assert response.status_code == 400


def test_move_rejects_non_numeric_angle(client, bus):
    response = client.post('/move', json={'channel': 0, 'angle': 'hi'})
    assert response.status_code == 400


def test_move_rejects_unknown_channel(client, bus):
    response = client.post('/move', json={'channel': 7, 'angle': 0})
    assert response.status_code == 400


def test_move_rejects_boolean_angle_disguised_as_number(client, bus):
    response = client.post('/move', json={'channel': 0, 'angle': True})
    assert response.status_code == 400


def test_centre_zeros_the_angle_regardless_of_payload(client, bus):
    client.post('/move', json={'channel': 0, 'angle': 45})
    response = client.post('/centre', json={'channel': 0, 'angle': 999})

    assert response.status_code == 200
    assert bus.positions[0] == 0


def test_health_reports_legtest_mode(client):
    response = client.get('/health')
    assert response.status_code == 200
    body = response.get_json()
    assert body['mode'] == 'legtest'
    assert body['armed'] is True
    assert body['leg'] == 'front-right'


def test_index_returns_html_with_leg_name(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'front-right' in response.data
    assert b'<!doctype html>' in response.data.lower() or b'<!DOCTYPE html>' in response.data


def test_shutdown_releases_all_configured_servos(bus):
    app = legtest.create_app('front-right', bus)
    client = app.test_client()
    client.post('/move', json={'channel': 0, 'angle': 20})
    client.post('/move', json={'channel': 2, 'angle': -10})

    legtest.release_all(app)

    assert bus.positions[0] is None
    assert bus.positions[2] is None
    assert ('release', 0) in bus.calls
    assert ('release', 2) in bus.calls
