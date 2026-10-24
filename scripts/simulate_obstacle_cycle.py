"""Exercise the real Phase 4 application with labeled synthetic sensor readings.
Uses a temporary DB and synthetic checked layout; never modifies user routes.
No physical alerts or audible speech are claimed by this diagnostic.
"""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from stride_backend.main import create_app
from stride_backend.settings import Settings


class Clock:
    def __init__(self):
        self.now = 10000

    def mono(self):
        return self.now

    def epoch(self):
        return 1700000000000 + self.now


def run_cycle():
    events = []
    clock = Clock()
    session, device, boot = 'simulation-session', 'simulation-controller', 'simulation-boot'
    ui = {'X-Session-Token': 'diagnostic-ui-only'}
    controller = {'X-Device-Token': 'diagnostic-controller-only'}
    with TemporaryDirectory(prefix='stride-obstacle-') as directory:
        settings = Settings(_env_file=None, local_dev=True,
                            database_path=Path(directory)/'diagnostic.sqlite3',
                            session_tokens={session: 'diagnostic-ui-only'},
                            controller_tokens={device: 'diagnostic-controller-only'},
                            controller_sessions={device: session})
        app = create_app(settings, clock=clock.mono, epoch_clock=clock.epoch)
        with TestClient(app) as client:
            def result(response):
                assert response.status_code == 200, response.text
                return response.json()

            def record(step, **data):
                events.append(dict(step=step, **data))

            sequence = 0
            def sample(distance):
                nonlocal sequence
                sequence += 1
                return result(client.post('/telemetry', headers=controller, json={
                    'device_id': device, 'boot_id': boot, 'sequence': sequence,
                    'uptime_ms': sequence*200, 'distance_cm': distance,
                    'measurement_valid': distance is not None, 'source': 'simulated'}))

            def navigation():
                return result(client.get('/memory', headers=ui, params={'session_id': session}))['navigation']

            def poll():
                return result(client.get(f'/devices/{device}/commands', headers=controller))['command']

            def action(name, previous):
                return result(client.post('/route', headers=ui, json={
                    'session_id': session, 'action_id': f'{name}-{sequence}-{clock.now}',
                    'action': name, 'navigation_id': previous['navigation_id'],
                    'expected_revision': previous['state_revision']}))

            def ack(command, state):
                return result(client.post(f'/devices/{device}/ack', headers=controller, json={
                    'device_id': device, 'command_id': command['command_id'], 'status': state}))

            result(client.post('/device/pair', headers=ui, json={'device_id': device, 'session_id': session}))
            for _ in range(3):
                sample(150)
            app.state.route_catalog.mark_checked('demo-hallway', 'SYNTHETIC TEST ONLY; not a physical route')
            route = result(client.post('/route', headers=ui, json={
                'session_id': session, 'route_id': 'demo-hallway', 'action': 'start', 'action_id': 'start'}))
            assert route['state'] == 'guiding'
            command = poll()
            assert command['kind'] == 'straight' and command['boot_id'] == boot
            assert command['device_id'] == device and 0 < command['remaining_ttl_ms'] <= 1500
            ack(command, 'received')
            assert ack(command, 'executed')['execution_reported'] is True
            assert poll() is None
            record('clear_route', state=route['state'], command=command['kind'], simulated_ack='executed', firmware_command=command)
            sample(20)
            blocked = navigation()
            stop = poll()
            assert blocked['state'] == 'blocked' and blocked['instruction'] is None
            assert blocked['guidance_event']['valid'] is False and stop['kind'] == 'stop'
            record('20cm_obstacle', state=blocked['state'], previous_guidance_valid=False, command=stop['kind'])
            clock.now += 1001
            status = result(client.get('/device/status', headers=ui, params={'device_id': device}))
            assert status['obstacle_state'] == 'unknown' and navigation()['state'] == 'blocked'
            assert status['current_distance_cm'] is None
            record('sensor_timeout', state='blocked', obstacle='unknown', current_distance_cm=None)
            sample(None)
            assert navigation()['state'] == 'blocked'
            record('invalid_no_echo', state='blocked', obstacle='unknown')
            for _ in range(2):
                sample(150)
                assert navigation()['state'] == 'blocked'
            sample(150)
            paused = navigation()
            assert paused['state'] == 'paused' and paused['instruction'] is None
            record('three_clear_samples', state='paused', automatic_resume=False)
            resumed = action('resume', paused)
            assert resumed['state'] == 'guiding'
            record('explicit_resume', state='guiding', instruction=resumed['instruction'])
    return {'source': 'simulated', 'application': 'real Phase 4 create_app',
            'physical_alert_verified': False, 'audible_speech_verified': False, 'events': events}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = run_cycle()
    encoded = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end='')
