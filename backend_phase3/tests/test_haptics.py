import sqlite3

import pytest
from fastapi.testclient import TestClient

from stride_backend.database import Database, SCHEMA
from stride_backend.main import create_app
from stride_backend.route_store import RouteCatalog
from tests.device_helpers import controller_settings, hardware_app
from tests.live_helpers import Clock


@pytest.fixture
def ready():
    with hardware_app() as h:
        h.route = h.ready_route()
        yield h


def test_directional_command_is_bound_short_lived_and_one_shot(ready):
    h = ready
    response = h.poll()
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    command = response.json()['command']
    assert command['kind'] == 'straight' and command['priority'] == 10
    assert command['device_id'] == 'sensor-1' and command['boot_id'] == 'boot-1'
    assert command['navigation_id'] == h.route['navigation_id']
    assert command['state_revision'] == h.route['state_revision']
    assert command['status'] == 'delivered' and 0 < command['remaining_ttl_ms'] <= 1000
    assert command['execution_reported'] is False and command['perception_verified'] is False
    assert h.poll().json()['command'] is None
    assert h.poll(path='/device/commands?device_id=sensor-1').json()['command'] is None


def test_wrong_device_polling_or_acknowledgment_is_denied(ready):
    h = ready
    command = h.poll().json()['command']
    assert h.client.get('/devices/sensor-1/commands', headers=h.device_headers('sensor-2')).status_code == 403
    assert h.ack(command, device='sensor-2').status_code == 409  # Own device has not paired.
    h.pair('sensor-2', 'other')
    h.clear('sensor-2')
    assert h.ack(command, device='sensor-2').status_code == 403
    assert h.client.post('/device/ack', headers=h.device_headers(), json={'device_id': 'sensor-2', 'command_id': command['command_id'], 'status': 'received'}).status_code == 403


def test_ack_lifecycle_and_duplicate_received_are_idempotent(ready):
    h = ready
    command = h.poll().json()['command']
    first = h.ack(command)
    assert first.status_code == 200
    assert first.json()['status'] == 'received' and first.json()['execution_reported'] is False
    again = h.ack(command).json()
    assert again['duplicate'] is True and again['status'] == 'received'
    executed = h.ack(command, 'executed').json()
    assert executed['status'] == 'executed' and executed['execution_reported'] is True
    assert executed['perception_verified'] is False
    assert h.ack(command, 'executed').json()['duplicate'] is True
    assert h.ack(command, 'rejected').status_code == 409
    assert h.status()['last_acknowledged_command_id'] == command['command_id']


def test_impossible_ack_transitions_and_unknown_ids_are_rejected(ready):
    h = ready
    command = h.status()['latest_command']
    assert command['status'] == 'issued'
    assert h.ack(command).status_code == 409
    command = h.poll().json()['command']
    assert h.ack(command, 'executed').status_code == 409
    assert h.ack({'command_id': 'unknown'}).status_code == 404
    assert h.ack(command, 'invalid').status_code == 422


def test_expiration_and_late_ack_never_revive_a_command(ready):
    h = ready
    command = h.poll().json()['command']
    h.ack(command)
    h.clock.advance(1000)  # TTL expires while the latest sensor sample is at its freshness boundary.
    assert h.poll().json()['command'] is None
    assert h.status()['latest_command']['status'] == 'expired'
    duplicate = h.ack(command).json()
    assert duplicate['duplicate'] is True and duplicate['status'] == 'expired'
    assert h.ack(command, 'executed').status_code == 409
    assert h.ack(command, 'expired').status_code == 200


def test_unpolled_expired_turn_is_not_replayed(ready):
    h = ready
    h.clock.advance(1000)
    assert h.poll().json()['command'] is None
    assert h.status()['latest_command']['status'] == 'expired'


@pytest.mark.parametrize('action', ['pause', 'stop'])
def test_pause_and_stop_supersede_turn_with_cancel(ready, action):
    h = ready
    turn = h.poll().json()['command']
    response = h.act(action, h.route)
    assert response.status_code == 200
    cancel = h.poll().json()['command']
    assert cancel['kind'] == 'cancel' and cancel['priority'] == 90
    assert cancel['command_id'] != turn['command_id']
    assert h.poll().json()['command'] is None
    assert h.ack(turn).status_code == 409


def test_danger_stop_preempts_delivered_direction(ready):
    h = ready
    turn = h.poll().json()['command']
    h.telemetry(distance=20)
    stop = h.poll().json()['command']
    assert stop['kind'] == 'stop' and stop['priority'] > turn['priority']
    assert stop['command_id'] != turn['command_id']
    assert h.ack(turn).status_code == 409
    assert h.ack(stop).status_code == 200


def test_revision_advance_invalidates_previous_ack_and_turn(ready):
    h = ready
    old = h.poll().json()['command']
    next_state = h.act('confirm', h.route).json()
    new = h.poll().json()['command']
    assert new['kind'] == 'left'
    assert new['state_revision'] == next_state['state_revision']
    assert h.ack(old).status_code == 409


def test_repeat_creates_one_new_cue_and_duplicate_action_does_not_create_more(ready):
    h = ready
    first = h.poll().json()['command']
    response = h.act('repeat', h.route, action_id='repeat-once')
    assert response.status_code == 200
    second = h.poll().json()['command']
    assert second['command_id'] != first['command_id']
    assert h.act('repeat', h.route, action_id='repeat-once').json()['duplicate'] is True
    assert h.poll().json()['command'] is None


def test_last_confirmation_cancels_without_reissuing_a_walking_command(ready):
    h = ready
    state = h.route
    for _ in range(3):
        state = h.act('confirm', state).json()
    assert state['state'] == 'completed'
    command = h.poll().json()['command']
    assert command['kind'] == 'cancel'


def test_controller_reboot_invalidates_old_command(ready):
    h = ready
    old = h.poll().json()['command']
    assert h.telemetry(boot_id='boot-2', sequence=0, uptime_ms=0).status_code == 200
    assert h.ack(old).status_code == 409
    current = h.poll().json()['command']
    assert current['boot_id'] == 'boot-2' and current['kind'] == 'cancel'


def test_command_and_ack_storage_stays_bounded_without_reissuing_current_event():
    with hardware_app(settings=controller_settings(max_commands_per_device=2)) as h:
        state = h.ready_route()
        for index in range(5):
            command = h.poll().json()['command']
            assert h.ack(command).status_code == 200
            assert h.ack(command, 'executed').status_code == 200
            state = h.act('repeat', state, action_id=f'repeat-{index}').json()
        assert h.poll().json()['command'] is not None
        assert h.poll().json()['command'] is None
        with h.app.state.database.transaction() as connection:
            assert connection.execute('SELECT COUNT(*) FROM haptic_commands WHERE device_id=?', ('sensor-1',)).fetchone()[0] <= 2
            assert connection.execute('SELECT COUNT(*) FROM haptic_acknowledgments').fetchone()[0] <= 4


def test_restart_cancels_prior_commands_and_preserves_route_progress():
    settings = controller_settings()
    clock = Clock()
    with hardware_app(settings=settings, clock=clock) as h:
        route = h.ready_route()
        route = h.act('confirm', route).json()
        command = h.poll().json()['command']
    replacement = create_app(settings, clock=clock.mono, epoch_clock=clock.epoch)
    with TestClient(replacement) as client:
        response = client.get('/devices/sensor-1/commands', headers={'X-Device-Token': 'sensor-secret-1'})
        assert response.status_code == 200
        returned = response.json()['command']
        assert returned is None or returned['kind'] == 'cancel'
        if returned:
            assert returned['command_id'] != command['command_id']
        memory = client.get('/memory?session_id=demo-1', headers={'X-Session-Token': 'route-ui-token'}).json()
        assert memory['navigation']['confirmed_checkpoint_count'] == 1
        assert memory['navigation']['state'] in {'paused', 'blocked'}


def test_additive_component_migration_preserves_phase3_routes(tmp_path):
    path = tmp_path / 'old-phase3.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA)
        connection.execute('PRAGMA user_version=1')
    database = Database(path)
    catalog = RouteCatalog(database)
    catalog.install_fixtures()
    catalog.mark_checked('demo-hallway', 'TEST ONLY: retained verification')
    database.initialize()
    database.initialize()
    with database.transaction() as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 1
        assert connection.execute("SELECT version FROM schema_migrations WHERE component='devices'").fetchone()[0] == 1
        assert connection.execute("SELECT checked FROM routes WHERE route_id='demo-hallway'").fetchone()[0] == 1
        assert connection.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0] == 5


def test_path_acknowledgment_supports_existing_logical_ack_names(ready):
    command = ready.poll().json()['command']
    assert ready.ack(command, 'accepted', path='/devices/sensor-1/ack').json()['status'] == 'received'
    assert ready.ack(command, 'completed', path='/devices/sensor-1/ack').json()['status'] == 'executed'


def test_invalid_ack_cannot_roll_back_a_stale_sensor_hold(ready):
    h = ready
    command = h.poll().json()['command']
    h.clock.advance(1001)
    assert h.ack(command).status_code == 409
    with h.app.state.database.transaction() as connection:
        assert connection.execute('SELECT state FROM navigation_sessions WHERE navigation_id=?', (h.route['navigation_id'],)).fetchone()[0] == 'blocked'


def test_unknown_sensor_does_not_downgrade_a_pending_danger_stop():
    with hardware_app(settings=controller_settings(haptic_ttl_ms=1500)) as h:
        h.ready_route()
        h.telemetry(distance=20)
        stop = h.poll().json()['command']
        assert stop['kind'] == 'stop'
        h.clock.advance(1001)
        assert h.status()['obstacle_state'] == 'unknown'
        assert h.status()['latest_command']['command_id'] == stop['command_id']
        h.telemetry(distance=None, valid=False)
        assert h.poll().json()['command'] is None
        assert h.status()['latest_command']['command_id'] == stop['command_id']
