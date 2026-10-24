import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from stride_backend.device_auth import ControllerAuth
from stride_backend.device_ingestion import ControllerBodyGuard
from stride_backend.main import create_app
from tests.device_helpers import controller_settings, hardware_app
from tests.live_helpers import Clock


@pytest.fixture
def hardware():
    with hardware_app() as h:
        yield h


def test_authenticated_telemetry_requires_explicit_pairing(hardware):
    h = hardware
    assert h.telemetry().status_code == 409
    assert h.pair().json() == {'device_id': 'sensor-1', 'session_id': 'demo-1', 'paired': True, 'duplicate': False}
    assert h.pair().json()['duplicate'] is True
    response = h.telemetry(distance=42)
    assert response.status_code == 200
    result = response.json()
    assert result['accepted'] is True and result['duplicate'] is False
    assert result['obstacle_state'] == 'danger' and result['telemetry_fresh'] is True
    assert result['physical_alert_verified'] is False
    state = h.status()
    assert state['current_distance_cm'] == 42 and state['sensor_valid'] is True
    assert state['availability'] == 'connected'
    assert state['battery_percent'] is None and state['firmware_version'] is None
    assert state['local_alerts_verified'] is False


def test_wrong_token_and_wrong_body_identity(hardware):
    h = hardware
    assert h.pair().status_code == 200
    data = {'device_id': 'sensor-1', 'boot_id': 'b', 'sequence': 1, 'uptime_ms': 0, 'distance_cm': 42, 'measurement_valid': True}
    for headers in ({}, {'X-Device-Token': 'wrong'}, {'X-Session-Token': 'route-ui-token'}, {'X-Device-Token': 'route-camera-token'}):
        assert h.client.post('/telemetry', headers=headers, json=data).status_code == 401
    assert h.client.post('/telemetry', headers=h.device_headers('sensor-2'), json=data).status_code == 403
    assert h.status()['last_telemetry_received_ms'] is None


def test_pairing_and_frontend_reads_are_session_scoped(hardware):
    h = hardware
    assert h.pair(device='sensor-2', session='demo-1').status_code == 403
    assert h.pair(device='sensor-2', session='other', headers=h.headers).status_code == 401
    assert h.pair().status_code == 200
    assert h.telemetry().status_code == 200
    assert h.status(frontend=True)['session_id'] == 'demo-1'
    assert h.client.get('/device/status?device_id=sensor-2', headers=h.headers).status_code == 401
    assert h.client.get('/device/status?device_id=sensor-2', headers=h.device_headers()).status_code == 403
    assert h.client.get('/device/status?device_id=sensor-1').status_code == 401
    assert h.client.get('/devices/sensor-1/commands', headers=h.headers).status_code == 401
    assert h.client.post('/device/pair', headers=h.device_headers(), json={'device_id': 'sensor-1', 'session_id': 'demo-1'}).status_code == 401


@pytest.mark.parametrize('field,value', [
    ('distance_cm', -1), ('distance_cm', float('nan')), ('distance_cm', float('inf')),
    ('battery_percent', 101), ('battery_percent', float('nan')), ('sequence', -1),
    ('sequence', True), ('sequence', 2**63), ('uptime_ms', -1), ('uptime_ms', 2**63), ('measurement_valid', 'true'),
])
def test_invalid_values_rejected(hardware, field, value):
    h = hardware
    h.pair()
    data = dict(device_id='sensor-1', boot_id='boot-1', sequence=1, uptime_ms=0, distance_cm=42, measurement_valid=True)
    data[field] = value
    response = h.client.post('/telemetry', headers={**h.device_headers(), 'Content-Type': 'application/json'}, content=json.dumps(data))
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'validation_error'


@pytest.mark.parametrize('distance,valid,reason', [(None, False, 'measurement_invalid'), (None, True, 'missing_distance'), (1, True, 'out_of_range'), (401, True, 'out_of_range')])
def test_unknown_measurements_never_mean_clear(hardware, distance, valid, reason):
    h = hardware
    h.pair()
    response = h.telemetry(distance=distance, valid=valid)
    assert response.status_code == 200
    assert response.json()['obstacle_state'] == 'unknown'
    state = h.status()
    assert state['measurement_reason'] == reason and state['current_distance_cm'] is None
    assert state['availability'] == 'connected' and state['sensor_valid'] is False
    assert state['last_reported_distance_cm'] == distance


def test_sensor_timeout_cannot_override_valid_distance(hardware):
    hardware.pair()
    assert hardware.telemetry(distance=150, sensor_status='timeout').json()['obstacle_state'] == 'unknown'


def test_duplicate_sequence_is_idempotent_and_does_not_refresh_timestamp(hardware):
    h = hardware
    h.pair()
    first = h.telemetry(sequence=10, uptime_ms=2000).json()
    h.clock.advance(1001)
    duplicate = h.telemetry(sequence=10, uptime_ms=2000).json()
    assert duplicate['duplicate'] is True
    assert duplicate['received_ms'] == first['received_ms']
    assert duplicate['telemetry_fresh'] is False and duplicate['obstacle_state'] == 'unknown'
    assert h.telemetry(sequence=9, uptime_ms=1800).status_code == 409
    assert h.telemetry(distance=42, sequence=10, uptime_ms=2000).status_code == 409
    assert h.telemetry(sequence=11, uptime_ms=1000).status_code == 409


def test_device_reboot_and_prior_boot_replay(hardware):
    h = hardware
    h.pair()
    assert h.telemetry(sequence=100, uptime_ms=20000).status_code == 200
    assert h.telemetry(boot_id='new-boot', sequence=0, uptime_ms=0).status_code == 200
    assert h.status()['boot_id'] == 'new-boot'
    assert h.telemetry(boot_id='boot-1', sequence=101, uptime_ms=20200).status_code == 409
    assert h.status()['boot_id'] == 'new-boot'


def test_bounded_telemetry_and_boot_history():
    with hardware_app(settings=controller_settings(telemetry_history_per_device=2, max_boots_per_device=2)) as h:
        h.pair()
        for _ in range(5):
            assert h.telemetry().status_code == 200
        assert h.telemetry(boot_id='b2').status_code == 200
        assert h.telemetry(boot_id='b3').status_code == 429
        with h.app.state.database.transaction() as connection:
            assert connection.execute('SELECT COUNT(*) FROM device_telemetry WHERE device_id=?', ('sensor-1',)).fetchone()[0] == 2
            assert connection.execute('SELECT COUNT(*) FROM device_boots WHERE device_id=?', ('sensor-1',)).fetchone()[0] == 2


def test_monotonic_freshness_historical_distance_and_no_poll_renewal(hardware):
    h = hardware
    h.pair()
    h.telemetry(distance=42, battery_percent=75, firmware_version='bench-v1')
    first = h.status()
    h.clock.advance(1001)
    state = h.status()
    assert state['obstacle_state'] == 'unknown' and state['current_distance_cm'] is None
    assert state['last_valid_distance_cm'] == 42 and state['last_valid_distance_age_ms'] == 1001
    assert state['battery_percent'] == 75 and state['firmware_version'] == 'bench-v1'
    assert h.status()['last_telemetry_received_ms'] == first['last_telemetry_received_ms']
    h.clock.advance(1000)
    assert h.status()['availability'] == 'stale'


def test_invalid_packet_can_show_connected_without_valid_sensor(hardware):
    h = hardware
    h.pair()
    h.telemetry(distance=42)
    h.clock.advance(100)
    h.telemetry(distance=None, valid=False)
    state = h.status()
    assert state['availability'] == 'connected'
    assert state['current_distance_cm'] is None and state['obstacle_state'] == 'unknown'
    assert state['last_valid_distance_cm'] == 42 and state['last_valid_distance_age_ms'] == 100


def test_malformed_json_body_limits_alias_and_old_valid_field(hardware):
    h = hardware
    h.pair()
    headers = {**h.device_headers(), 'Content-Type': 'application/json'}
    assert h.client.post('/telemetry', headers=headers, content='{broken').status_code == 422
    assert h.client.post('/telemetry', headers=headers, content='x' * 5000).status_code == 413
    assert h.client.post('/telemetry', headers=h.device_headers(), content='wrong').status_code == 415
    assert h.telemetry(path='/device/telemetry').status_code == 200
    data = dict(device_id='sensor-1', boot_id='boot-1', sequence=100, uptime_ms=20000, distance_cm=42, valid=True, source='fixture')
    assert h.client.post('/telemetry', headers=h.device_headers(), json=data).status_code == 200
    assert h.client.post('/telemetry', headers=h.device_headers(), json={**data, 'session_id': 'other'}).status_code == 422


def test_streaming_payload_is_bounded_before_parsing():
    settings = controller_settings()
    chunks = iter([{'type': 'http.request', 'body': b'x' * 4096, 'more_body': True}, {'type': 'http.request', 'body': b'x', 'more_body': False}])
    sent = []

    async def forbidden(*args):
        raise AssertionError('Parser must not receive an oversized body')

    async def receive():
        return next(chunks)

    async def send(message):
        sent.append(message)

    scope = {'type': 'http', 'method': 'POST', 'path': '/telemetry', 'headers': [(b'x-device-token', b'sensor-secret-1'), (b'content-type', b'application/json')]}
    clock = Clock()
    asyncio.run(ControllerBodyGuard(forbidden, settings, ControllerAuth(settings), clock.mono, clock.epoch)(scope, receive, send))
    assert sent[0]['status'] == 413


def test_restart_does_not_make_persisted_observation_fresh():
    settings = controller_settings()
    clock = Clock()
    with hardware_app(settings=settings, clock=clock) as h:
        h.pair()
        h.telemetry(distance=42)
    replacement = create_app(settings, clock=clock.mono, epoch_clock=clock.epoch)
    with TestClient(replacement) as client:
        response = client.get('/device/status?device_id=sensor-1', headers={'X-Device-Token': 'sensor-secret-1'})
        state = response.json()
        assert state['telemetry_fresh'] is False and state['obstacle_state'] == 'unknown'
        assert state['last_valid_distance_cm'] == 42
        duplicate = client.post('/telemetry', headers={'X-Device-Token': 'sensor-secret-1'}, json={
            'device_id': 'sensor-1', 'boot_id': 'boot-1', 'sequence': 1, 'uptime_ms': 200,
            'distance_cm': 42, 'measurement_valid': True, 'source': 'fixture',
        }).json()
        assert duplicate['duplicate'] is True and duplicate['telemetry_fresh'] is False


def test_production_requires_distinct_device_credentials_and_provisioned_owner():
    for changes in (
        {'controller_tokens': {}}, {'controller_tokens': {'sensor-1': 'route-camera-token', 'sensor-2': 'sensor-secret-2'}},
        {'controller_tokens': {'sensor-1': 'route-ui-token', 'sensor-2': 'sensor-secret-2'}},
        {'controller_sessions': {'sensor-1': 'demo-1', 'sensor-2': 'demo-1'}},
    ):
        with pytest.raises(ValidationError):
            controller_settings(local_dev=False, **changes)


def test_explicit_tokenless_local_mode_still_requires_provisioned_device():
    settings = controller_settings(controller_tokens={}, session_tokens={})
    with hardware_app(settings=settings) as h:
        assert h.client.post('/device/pair', json={'device_id': 'sensor-1', 'session_id': 'demo-1'}).status_code == 200
        data = {'device_id': 'sensor-1', 'boot_id': 'boot', 'sequence': 1, 'uptime_ms': 0, 'distance_cm': 150, 'measurement_valid': True, 'source': 'fixture'}
        assert h.client.post('/telemetry', headers={'X-Device-ID': 'sensor-1'}, json=data).status_code == 200
        assert h.client.post('/telemetry', headers={'X-Device-ID': 'unknown'}, json=data).status_code == 401


def test_existing_browser_cookie_pairs_and_reads_but_cannot_impersonate_controller(hardware):
    h = hardware
    login = h.client.post('/auth/session', json={'session_id': 'demo-1', 'session_token': 'route-ui-token'})
    assert login.status_code == 200
    assert h.client.post('/device/pair', json={'device_id': 'sensor-1', 'session_id': 'demo-1'}).status_code == 200
    assert h.client.get('/device/status?device_id=sensor-1').status_code == 200
    assert h.client.get('/device/status?device_id=sensor-2').status_code == 401
    assert h.client.get('/devices/sensor-1/commands').status_code == 401
    assert h.client.post('/telemetry', json={}).status_code == 401


def test_production_accepts_scoped_real_telemetry_and_never_exposes_secrets():
    with hardware_app(settings=controller_settings(local_dev=False)) as h:
        assert h.pair().status_code == 200
        assert h.telemetry(source='real').status_code == 200
        assert h.telemetry(source='fixture').status_code == 422
        status = h.status()
        assert status['expected_telemetry_hz'] == 5
        assert 'sensor-secret-1' not in str(status) and 'route-ui-token' not in str(status)


def test_unauthorized_controller_body_is_never_read():
    settings = controller_settings()
    sent = []

    async def forbidden(*args):
        raise AssertionError('Unauthenticated controller body must not be read')

    async def send(message):
        sent.append(message)

    clock = Clock()
    scope = {'type': 'http', 'method': 'POST', 'path': '/telemetry', 'headers': []}
    asyncio.run(ControllerBodyGuard(forbidden, settings, ControllerAuth(settings), clock.mono, clock.epoch)(scope, forbidden, send))
    assert sent[0]['status'] == 401


def test_diagnostics_are_bounded_and_finite(hardware):
    hardware.pair()
    assert hardware.telemetry(diagnostics={'text': 'x' * 1100}).status_code == 422
    assert hardware.telemetry(diagnostics={f'k{index}': index for index in range(9)}).status_code == 422


def test_duplicate_payload_is_independent_of_diagnostic_key_order(hardware):
    hardware.pair()
    assert hardware.telemetry(sequence=1, uptime_ms=200, diagnostics={'a': 1, 'b': 2}).status_code == 200
    response = hardware.telemetry(sequence=1, uptime_ms=200, diagnostics={'b': 2, 'a': 1})
    assert response.status_code == 200 and response.json()['duplicate'] is True


def test_reprovisioned_controller_requires_new_authorized_pairing():
    settings = controller_settings()
    clock = Clock()
    with hardware_app(settings=settings, clock=clock) as h:
        assert h.pair().status_code == 200
    replacement_settings = controller_settings(controller_tokens={'replacement': 'new-device-secret'}, controller_sessions={'replacement': 'demo-1'})
    app = create_app(replacement_settings, clock=clock.mono, epoch_clock=clock.epoch)
    with TestClient(app) as client:
        response = client.post('/device/pair', headers={'X-Session-Token': 'route-ui-token'}, json={'device_id': 'replacement', 'session_id': 'demo-1'})
        assert response.status_code == 200
        assert response.json()['paired'] is True
