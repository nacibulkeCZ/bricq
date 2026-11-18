"""Route-level tests for the calibrate Flask app, using a FakeServoBus."""
import pytest

import hardware
from modes import calibrate


@pytest.fixture(autouse=True)
def _reset_trims():
    """Calibrate mutates hardware.SERVO_TRIMS in place; isolate tests from one another."""
    saved = dict(hardware.SERVO_TRIMS)
    yield
    hardware.SERVO_TRIMS.clear()
    hardware.SERVO_TRIMS.update(saved)


@pytest.fixture
def bus():
    return hardware.FakeServoBus()


@pytest.fixture
def client(bus):
    app = calibrate.create_app(bus)
    return app.test_client()


def test_state_lists_all_eight_servos_with_leg_and_joint_labels(client):
    body = client.get('/state').get_json()
    labels = {(s['leg'], s['joint']): s['channel'] for s in body['servos']}
    assert labels[('front-right', 'thigh')] == 0
    assert labels[('front-right', 'knee')] == 2
    assert labels[('back-right', 'thigh')] == 4
    assert labels[('back-right', 'knee')] == 6
    assert labels[('back-left', 'knee')] == 9
    assert labels[('back-left', 'thigh')] == 11
    assert labels[('front-left', 'knee')] == 13
    assert labels[('front-left', 'thigh')] == 15


def test_state_starts_with_servos_released(client):
    body = client.get('/state').get_json()
    for servo in body['servos']:
        assert servo['commanded'] is None


def test_trim_update_writes_to_hardware_and_responds_with_new_dict(client):
    response = client.post('/trim', json={'channel': 0, 'trim': 7})
    assert response.status_code == 200
    body = response.get_json()
    channel_zero = next(s for s in body['servos'] if s['channel'] == 0)
    assert channel_zero['trim'] == 7
    assert hardware.SERVO_TRIMS[0] == 7
    assert '0: 7' in body['trim_dict_literal']


def test_trim_update_applies_live_only_when_servo_is_engaged(client, bus):
    # Not engaged yet — trim alone doesn't move the servo.
    client.post('/trim', json={'channel': 0, 'trim': 10})
    assert bus.positions.get(0) is None
    # Engage via zero-all, trim then takes effect on next adjustment.
    client.post('/zero-all')
    assert bus.positions[0] == 10  # 0° commanded + trim 10
    client.post('/trim', json={'channel': 0, 'trim': -5})
    assert bus.positions[0] == -5


def test_zero_all_commands_zero_plus_trim_on_every_channel(client, bus):
    client.post('/trim', json={'channel': 0, 'trim': 3})
    client.post('/trim', json={'channel': 9, 'trim': -8})
    client.post('/zero-all')
    assert bus.positions[0] == 3
    assert bus.positions[9] == -8
    # Untrimmed channels land exactly at zero.
    for channel in (2, 4, 6, 11, 13, 15):
        assert bus.positions[channel] == 0


def test_release_frees_every_servo_and_marks_as_uncommanded(client, bus):
    client.post('/zero-all')
    response = client.post('/release')
    assert response.status_code == 200
    body = response.get_json()
    for servo in body['servos']:
        assert servo['commanded'] is None
    for channel in (0, 2, 4, 6, 9, 11, 13, 15):
        assert bus.positions[channel] is None


def test_trim_rejects_out_of_range(client):
    response = client.post('/trim', json={'channel': 0, 'trim': 100})
    assert response.status_code == 400


def test_trim_rejects_boolean(client):
    response = client.post('/trim', json={'channel': 0, 'trim': True})
    assert response.status_code == 400


def test_trim_rejects_unknown_channel(client):
    response = client.post('/trim', json={'channel': 99, 'trim': 0})
    assert response.status_code == 400


def test_trim_dict_literal_is_python_parseable(client):
    client.post('/trim', json={'channel': 0, 'trim': 7})
    client.post('/trim', json={'channel': 9, 'trim': -3})
    literal = client.get('/state').get_json()['trim_dict_literal']
    namespace = {}
    exec(literal, namespace)
    assert namespace['SERVO_TRIMS'][0] == 7
    assert namespace['SERVO_TRIMS'][9] == -3


def test_health_reports_calibrate_mode(client):
    body = client.get('/health').get_json()
    assert body['mode'] == 'calibrate'


def test_index_returns_html(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b'<!doctype html>' in response.data.lower() or b'<!DOCTYPE html>' in response.data


def test_trimmed_helper_applies_to_servo_bus_set_angle():
    """ServoBus.set_angle applies the trim transparently; every mode benefits."""
    hardware.SERVO_TRIMS[0] = 5
    bus = hardware.FakeServoBus()
    bus.set_angle(0, 10)
    assert bus.positions[0] == 15


def test_trimmed_helper_clamps_to_angle_range():
    hardware.SERVO_TRIMS[0] = 40
    bus = hardware.FakeServoBus()
    bus.set_angle(0, 80)
    lo, hi = hardware.ANGLE_RANGE
    assert bus.positions[0] == hi
