from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

from stride_backend.obstacles import classify
from tests.device_helpers import controller_settings, hardware_app


@pytest.mark.parametrize('distance,valid,previous,expected', [
    (150, True, 'unknown', 'clear'), (100, True, 'clear', 'caution'),
    (50, True, 'clear', 'danger'), (51, True, 'danger', 'danger'),
    (55, True, 'danger', 'danger'), (56, True, 'danger', 'caution'),
    (104, True, 'caution', 'caution'), (106, True, 'caution', 'clear'),
    (20, True, 'clear', 'danger'), (20, False, 'clear', 'unknown'),
    (None, True, 'clear', 'unknown'), (401, True, 'clear', 'unknown'),
])
def test_thresholds_hysteresis_and_immediate_danger(distance, valid, previous, expected):
    state, _, _ = classify(distance, valid, None, previous, controller_settings())
    assert state == expected


def test_danger_blocks_without_losing_progress_and_clear_requires_recovery():
    with hardware_app() as h:
        route = h.ready_route()
        route = h.act('confirm', route).json()
        assert route['confirmed_checkpoint_count'] == 1
        result = h.telemetry(distance=37.5)
        assert result.json()['obstacle_state'] == 'danger'
        blocked = h.memory()['navigation']
        assert blocked['state'] == 'blocked'
        assert blocked['confirmed_checkpoint_count'] == 1
        assert blocked['instruction'] is None and blocked['haptic_direction'] is None
        assert blocked['guidance_event']['valid'] is False
        assert blocked['sensor_monitoring'] == 'fresh_measurement'
        assert h.act('confirm', blocked).status_code == 409
        h.clock.advance(1001)
        assert h.status()['obstacle_state'] == 'unknown'
        assert h.memory()['navigation']['state'] == 'blocked'
        for count in (1, 2):
            h.telemetry(distance=150)
            assert h.status()['recovery_clear_count'] == count
            assert h.memory()['navigation']['state'] == 'blocked'
        h.telemetry(distance=150)
        paused = h.memory()['navigation']
        assert paused['state'] == 'paused' and paused['confirmed_checkpoint_count'] == 1
        assert paused['instruction'] is None
        resumed = h.act('resume', paused).json()
        assert resumed['state'] == 'guiding' and resumed['confirmed_checkpoint_count'] == 1


@pytest.mark.parametrize('distance,valid', [(80, True), (None, False), (500, True)])
def test_caution_unknown_and_unsupported_measurements_hold_navigation(distance, valid):
    with hardware_app() as h:
        h.ready_route()
        assert h.telemetry(distance=distance, valid=valid).status_code == 200
        route = h.memory()['navigation']
        assert route['state'] == 'blocked' and route['instruction'] is None
        assert h.act('confirm', route).status_code == 409


def test_paired_route_without_measurement_is_explicitly_held():
    with hardware_app() as h:
        h.pair()
        h.check()
        route = h.start().json()
        assert route['state'] == 'blocked' and route['instruction'] is None
        assert route['sensor_monitoring'] == 'unknown'
        assert route['paired_device_id'] == 'sensor-1'


def test_unpaired_device_does_not_pretend_sensor_monitoring_is_active():
    with hardware_app() as h:
        h.check()
        route = h.start().json()
        assert route['state'] == 'guiding' and route['sensor_monitoring'] == 'not_associated'
        assert route['paired_device_id'] is None
        assert h.status()['availability'] == 'unknown'
        assert h.poll().status_code == 409


def test_danger_and_confirmation_are_serialized_without_unsafe_cue():
    with hardware_app() as h:
        route = h.ready_route()
        barrier = Barrier(2)

        def confirm():
            barrier.wait(timeout=3)
            return h.act('confirm', route)

        def danger():
            barrier.wait(timeout=3)
            return h.telemetry(distance=20)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(confirm)
            second = pool.submit(danger)
            confirmation, telemetry = first.result(timeout=5), second.result(timeout=5)
        assert confirmation.status_code in (200, 409)
        assert telemetry.status_code == 200
        current = h.memory()['navigation']
        assert current['state'] == 'blocked' and current['instruction'] is None
        assert current['confirmed_checkpoint_count'] <= 1
        command = h.poll().json()['command']
        assert command['kind'] == 'stop' and command['priority'] == 100


def test_vision_stop_does_not_erase_blocked_route_or_sensor_progress():
    with hardware_app() as h:
        route = h.ready_route()
        assert h.client.post('/vision', headers=h.headers, json={'session_id': 'demo-1', 'action_id': 'v1', 'action': 'start'}).status_code == 200
        h.telemetry(distance=20)
        blocked = h.memory()['navigation']
        assert h.client.post('/vision', headers=h.headers, json={'session_id': 'demo-1', 'action_id': 'v2', 'action': 'stop'}).status_code == 200
        assert h.memory()['navigation']['navigation_id'] == route['navigation_id']
        assert h.memory()['navigation']['state_revision'] == blocked['state_revision']
        assert h.memory()['navigation']['state'] == 'blocked'


def test_fixed_monitor_expires_feed_without_a_status_poll():
    with hardware_app(settings=controller_settings(device_monitor_interval_ms=20)) as h:
        h.ready_route()
        ran = Event()
        original = h.app.state.devices.maintenance

        def observed():
            original()
            ran.set()

        h.app.state.devices.maintenance = observed
        h.clock.advance(1001)
        assert ran.wait(2), 'Fixed device monitor did not run'
        with h.app.state.database.transaction() as connection:
            state = connection.execute('SELECT state FROM navigation_sessions').fetchone()[0]
            assert state == 'blocked'
        task = h.app.state.device_monitor.task
    assert task.done()


def test_sensor_audit_retention_preserves_explicit_checkpoint_confirmations():
    with hardware_app(settings=controller_settings(device_events_per_navigation=2)) as h:
        route = h.ready_route()
        route = h.act('confirm', route).json()
        for _ in range(4):
            h.telemetry(distance=20)
            h.clear()
            paused = h.memory()['navigation']
            assert paused['confirmed_checkpoint_count'] == 1
            route = h.act('resume', paused).json()
        with h.app.state.database.transaction() as connection:
            rows = connection.execute('SELECT action FROM route_events WHERE navigation_id=?', (route['navigation_id'],)).fetchall()
            sensor = [row[0] for row in rows if row[0].startswith('sensor_') or row[0].startswith('obstacle_') or row[0] == 'controller_reboot']
            assert len(sensor) <= 2
            assert sum(row[0] == 'confirm' for row in rows) == 1
            assert sum(row[0] == 'resume' for row in rows) == 4


def test_existing_obstacle_interface_cannot_bypass_paired_recovery_rule():
    from stride_backend.route_models import ObstacleObservation
    with hardware_app() as h:
        h.ready_route()
        h.telemetry(distance=20)
        blocked = h.memory()['navigation']
        result = h.app.state.navigation.apply_obstacle(
            'demo-1', blocked['navigation_id'], blocked['state_revision'],
            ObstacleObservation(fresh=True, valid=True, obstacle=False),
        )
        assert result.state == 'blocked' and result.instruction is None
        assert result.state_revision == h.memory()['navigation']['state_revision']
