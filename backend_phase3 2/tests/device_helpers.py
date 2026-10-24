from contextlib import contextmanager

from stride_backend.settings import Settings
from tests.navigation_helpers import NavigationHarness, navigation_app


def controller_settings(**overrides):
    values = dict(
        _env_file=None, local_dev=True, device_token='route-camera-token',
        session_tokens={'demo-1': 'route-ui-token', 'other': 'other-ui-token'},
        controller_tokens={'sensor-1': 'sensor-secret-1', 'sensor-2': 'sensor-secret-2'},
        controller_sessions={'sensor-1': 'demo-1', 'sensor-2': 'other'},
        device_monitor_interval_ms=1000,
    )
    values.update(overrides)
    return Settings(**values)


class HardwareHarness(NavigationHarness):
    def __init__(self, original):
        super().__init__(original.app, original.client, original.clock)
        self.sequences = {'sensor-1': 0, 'sensor-2': 0}

    @staticmethod
    def device_headers(device='sensor-1'):
        return {'X-Device-Token': 'sensor-secret-1' if device == 'sensor-1' else 'sensor-secret-2'}

    def pair(self, device='sensor-1', session='demo-1', headers=None):
        if headers is None:
            headers = self.headers if session == 'demo-1' else {'X-Session-Token': 'other-ui-token'}
        return self.client.post('/device/pair', headers=headers, json={'device_id': device, 'session_id': session})

    def telemetry(self, distance=150, valid=True, device='sensor-1', path='/telemetry', **overrides):
        self.sequences[device] += 1
        sequence = self.sequences[device]
        data = dict(device_id=device, boot_id='boot-1', sequence=sequence,
                    uptime_ms=sequence * 200, distance_cm=distance, measurement_valid=valid, source='fixture')
        data.update(overrides)
        return self.client.post(path, headers=self.device_headers(device), json=data)

    def clear(self, device='sensor-1'):
        for _ in range(self.app.state.settings.obstacle_recovery_samples):
            response = self.telemetry(device=device)
            assert response.status_code == 200, response.text

    def status(self, device='sensor-1', frontend=False):
        headers = self.headers if frontend else self.device_headers(device)
        response = self.client.get('/device/status', params={'device_id': device}, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    def poll(self, device='sensor-1', path=None):
        return self.client.get(path or f'/devices/{device}/commands', headers=self.device_headers(device))

    def ack(self, command, status='received', device='sensor-1', path='/device/ack'):
        return self.client.post(path, headers=self.device_headers(device), json={
            'device_id': device, 'command_id': command['command_id'], 'status': status,
        })

    def ready_route(self):
        assert self.pair().status_code == 200
        self.clear()
        self.check()
        response = self.start()
        assert response.status_code == 200, response.text
        assert response.json()['state'] == 'guiding'
        return response.json()


@contextmanager
def hardware_app(*, settings=None, clock=None):
    with navigation_app(settings=settings or controller_settings(), clock=clock) as original:
        yield HardwareHarness(original)
