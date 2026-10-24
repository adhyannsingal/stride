from contextlib import contextmanager
from itertools import count

from fastapi.testclient import TestClient

from stride_backend.main import create_app
from stride_backend.settings import Settings
from tests.live_helpers import Clock


class NavigationHarness:
    def __init__(self, app, client, clock):
        self.app = app
        self.client = client
        self.clock = clock
        self.headers = {"X-Session-Token": "route-ui-token"}
        self.ids = count()

    def start(self, route="demo-hallway", **extra):
        return self.client.post("/route", headers=self.headers, json={
            "session_id": "demo-1", "route_id": route, "action": "start",
            "action_id": f"start-{next(self.ids)}", **extra,
        })

    def act(self, action, previous, **extra):
        return self.client.post("/route", headers=self.headers, json={
            "session_id": "demo-1", "action": action, "action_id": f"{action}-{next(self.ids)}",
            "navigation_id": previous["navigation_id"], "expected_revision": previous["state_revision"], **extra,
        })

    def memory(self, **params):
        response = self.client.get("/memory", headers=self.headers, params={"session_id": "demo-1", **params})
        assert response.status_code == 200, response.text
        return response.json()

    def check(self, route="demo-hallway"):
        return self.app.state.route_catalog.mark_checked(route, "TEST ONLY: deterministic fixture layout verification")


@contextmanager
def navigation_app(*, settings=None, detector=None, clock=None):
    clock = clock or Clock()
    settings = settings or Settings(
        _env_file=None, local_dev=True, device_token="route-camera-token",
        session_tokens={"demo-1": "route-ui-token", "other": "other-ui-token"},
    )
    app = create_app(settings, detector, clock=clock.mono, epoch_clock=clock.epoch)
    with TestClient(app) as client:
        yield NavigationHarness(app, client, clock)
