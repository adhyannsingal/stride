from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from stride_backend.errors import BackendError
from stride_backend.main import create_app
from stride_backend.route_models import ObstacleObservation
from tests.navigation_helpers import navigation_app


@pytest.fixture
def nav():
    with navigation_app() as harness:
        yield harness


def test_route_listing_and_unchecked_rejection(nav):
    response = nav.client.get("/routes?session_id=demo-1", headers=nav.headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    routes = response.json()["routes"]
    assert {route["route_id"] for route in routes} == {"demo-hallway", "demo-tabletop"}
    assert all(route["checked"] is False and route["demo_fixture"] is True for route in routes)
    response = nav.start()
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "route_unchecked"
    assert nav.memory()["navigation"] is None


def test_start_checked_route_with_structured_guidance(nav):
    nav.check()
    response = nav.start()
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["state"] == "guiding" and state["state_revision"] == 1
    assert state["confirmed_checkpoint_count"] == 0 and state["total_checkpoints"] == 3
    assert state["current_checkpoint"]["checkpoint_id"] == "demo-hallway:A"
    assert state["instruction"] == "Proceed to checkpoint A."
    assert state["haptic_direction"] == "straight"
    assert state["guidance_event"]["valid"] is True
    assert state["guidance_event_id"] == state["guidance_event"]["event_id"]
    assert state["physical_position_known"] is False
    assert state["progress_source"] == "user_confirmation"


def test_three_checkpoint_route_requires_three_confirmations(nav):
    nav.check()
    state = nav.start().json()
    for confirmed in (1, 2, 3):
        response = nav.act("confirm", state)
        assert response.status_code == 200, response.text
        state = response.json()
        assert state["confirmed_checkpoint_count"] == confirmed
        assert len(state["confirmed_checkpoints"]) == confirmed
        assert state["state_revision"] == confirmed + 1
        assert state["state"] == ("completed" if confirmed == 3 else "guiding")
    assert state["current_checkpoint"] is None
    assert state["instruction"] is None and state["haptic_direction"] is None
    assert state["guidance_event"]["valid"] is False
    assert nav.act("confirm", state).status_code == 409
    assert [event["action"] for event in nav.memory(include_events=True)["route_events"]] == ["start", "confirm", "confirm", "confirm"]


def test_repeat_does_not_change_progress_revision_or_progress_history(nav):
    nav.check()
    first = nav.start().json()
    repeated = nav.act("repeat", first, action_id="repeat-once").json()
    assert repeated["instruction"] == first["instruction"]
    assert repeated["state_revision"] == first["state_revision"]
    assert repeated["confirmed_checkpoint_count"] == 0
    assert repeated["guidance_event_id"] != first["guidance_event_id"]
    duplicate = nav.act("repeat", first, action_id="repeat-once").json()
    assert duplicate["duplicate"] is True
    assert duplicate["guidance_event_id"] == repeated["guidance_event_id"]
    assert len(nav.memory(include_events=True)["route_events"]) == 1


def test_pause_resume_preserve_progress_and_invalidate_cues(nav):
    nav.check()
    state = nav.act("confirm", nav.start().json()).json()
    paused = nav.act("pause", state).json()
    assert paused["state"] == "paused" and paused["confirmed_checkpoint_count"] == 1
    assert paused["instruction"] is None and paused["guidance_event"]["valid"] is False
    resumed = nav.act("resume", paused).json()
    assert resumed["state"] == "guiding" and resumed["confirmed_checkpoint_count"] == 1
    assert resumed["instruction"] == state["instruction"]
    assert resumed["guidance_event_id"] != state["guidance_event_id"]


def test_stop_keeps_history_and_prevents_old_actions_modifying_later_navigation(nav):
    nav.check()
    first = nav.start(action_id="first-start").json()
    first = nav.act("confirm", first).json()
    stopped = nav.act("stop", first).json()
    assert stopped["state"] == "idle" and stopped["confirmed_checkpoint_count"] == 1
    assert stopped["instruction"] is None and stopped["guidance_event"]["valid"] is False
    second = nav.start(expected_revision=stopped["state_revision"]).json()
    assert second["navigation_id"] != first["navigation_id"]
    assert second["state_revision"] > stopped["state_revision"]
    assert nav.act("confirm", first).status_code == 409
    assert nav.start(action_id="unknown-delayed-start").status_code == 409
    duplicate = nav.start(action_id="first-start").json()
    assert duplicate["duplicate"] is True and duplicate["navigation_id"] == second["navigation_id"]
    memory = nav.memory(include_events=True)
    assert memory["navigation"]["confirmed_checkpoint_count"] == 0
    assert memory["previous_navigation"][0]["confirmed_checkpoint_count"] == 1


@pytest.mark.parametrize("actions,invalid", [
    (["start"], "resume"), (["start", "pause"], "confirm"),
    (["start", "pause"], "repeat"), (["start", "pause"], "pause"),
    (["start", "stop"], "confirm"), (["start", "stop"], "resume"),
])
def test_invalid_transitions_return_409(nav, actions, invalid):
    nav.check()
    state = None
    for action in actions:
        state = nav.start().json() if action == "start" else nav.act(action, state).json()
    response = nav.act(invalid, state, action_id="invalid")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"
    assert nav.act(invalid, state, action_id="invalid").json() == response.json()


def test_duplicate_confirmation_and_conflicting_action_ids(nav):
    nav.check()
    initial = nav.start().json()
    first = nav.act("confirm", initial, action_id="confirm-once").json()
    duplicate = nav.act("confirm", initial, action_id="confirm-once").json()
    assert duplicate["duplicate"] is True
    assert duplicate["confirmed_checkpoint_count"] == 1
    assert duplicate["guidance_event_id"] == first["guidance_event_id"]
    assert nav.act("pause", initial, action_id="confirm-once").status_code == 409


def test_simultaneous_distinct_confirmations_only_advance_once(nav):
    nav.check()
    state = nav.start().json()
    barrier = Barrier(2)

    def confirm(identifier):
        barrier.wait(timeout=3)
        return nav.client.post("/route", headers=nav.headers, json={
            "session_id": "demo-1", "navigation_id": state["navigation_id"],
            "expected_revision": state["state_revision"], "action": "confirm", "action_id": identifier,
        })

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(confirm, identifier) for identifier in ("tap-1", "tap-2")]
        responses = [future.result(timeout=5) for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert nav.memory()["navigation"]["confirmed_checkpoint_count"] == 1


def test_blocked_requires_valid_fresh_clear_then_explicit_resume(nav):
    nav.check()
    state = nav.start().json()
    controller = nav.app.state.navigation
    blocked = controller.apply_obstacle("demo-1", state["navigation_id"], state["state_revision"], ObstacleObservation(fresh=True, valid=True, obstacle=True)).model_dump(mode="json")
    assert blocked["state"] == "blocked" and blocked["instruction"] is None
    assert nav.act("confirm", blocked).status_code == 409
    assert nav.act("repeat", blocked).status_code == 409
    assert nav.act("resume", blocked).status_code == 409
    for observation in (
        ObstacleObservation(fresh=False, valid=True, obstacle=False),
        ObstacleObservation(fresh=True, valid=False, obstacle=False),
        ObstacleObservation(fresh=True, valid=True, obstacle=None),
    ):
        unknown = controller.apply_obstacle("demo-1", blocked["navigation_id"], blocked["state_revision"], observation)
        assert unknown.state == "blocked" and unknown.instruction is None
    clear = controller.apply_obstacle("demo-1", blocked["navigation_id"], blocked["state_revision"], ObstacleObservation(fresh=True, valid=True, obstacle=False)).model_dump(mode="json")
    assert clear["state"] == "paused" and clear["instruction"] is None
    assert nav.act("resume", clear).json()["state"] == "guiding"


def test_database_restart_recovers_paused_progress_without_old_cue(nav):
    nav.check()
    state = nav.act("confirm", nav.start().json()).json()
    from fastapi.testclient import TestClient
    # Single-process deployment: this simulates a later app opening the same DB.
    replacement = create_app(nav.app.state.settings, clock=nav.clock.mono, epoch_clock=nav.clock.epoch)
    with TestClient(replacement) as client:
        response = client.get("/memory?session_id=demo-1", headers=nav.headers)
        restored = response.json()["navigation"]
        assert restored["state"] == "paused"
        assert restored["confirmed_checkpoint_count"] == 1
        assert restored["state_revision"] > state["state_revision"]
        assert restored["instruction"] is None
        result = client.post("/route", headers=nav.headers, json={
            "session_id": "demo-1", "navigation_id": restored["navigation_id"], "action_id": "restart-resume",
            "action": "resume", "expected_revision": restored["state_revision"],
        })
        assert result.status_code == 200
        assert result.json()["current_checkpoint"]["checkpoint_id"] == "demo-hallway:B"


def test_guidance_expiry_and_repeat_refresh_are_explicit(nav):
    nav.check()
    state = nav.start().json()
    nav.clock.advance(nav.app.state.settings.guidance_ttl_ms + 1)
    stale = nav.memory()["navigation"]
    assert stale["guidance_event"]["valid"] is False and stale["instruction"] is None
    assert stale["guidance_event_id"] == state["guidance_event_id"]
    assert nav.act("repeat", stale).json()["guidance_event"]["valid"] is True


def test_route_and_vision_lifecycles_are_independent(nav):
    nav.check()
    assert nav.client.post("/vision", headers=nav.headers, json={"session_id": "demo-1", "action_id": "vision-start", "action": "start"}).status_code == 200
    stopped = nav.act("stop", nav.start().json()).json()
    assert nav.client.get("/vision/latest?session_id=demo-1", headers=nav.headers).json()["state"] == "active"
    route = nav.start(expected_revision=stopped["state_revision"]).json()
    assert nav.client.post("/vision", headers=nav.headers, json={"session_id": "demo-1", "action_id": "vision-stop", "action": "stop"}).status_code == 200
    assert nav.memory()["navigation"]["navigation_id"] == route["navigation_id"]
    assert nav.memory()["navigation"]["state"] == "guiding"


def test_new_routes_require_auth_and_isolate_sessions(nav):
    nav.check()
    nav.start()
    for path in ("/routes", "/memory"):
        assert nav.client.get(path, params={"session_id": "demo-1"}).status_code == 401
        assert nav.client.get(path, params={"session_id": "other"}, headers=nav.headers).status_code == 401
    other = nav.client.get("/memory?session_id=other&include_events=true", headers={"X-Session-Token": "other-ui-token"}).json()
    assert other["navigation"] is None and other["route_events"] == []
    assert nav.client.post("/route", headers=nav.headers, json={"session_id": "other", "route_id": "demo-hallway", "action": "start", "action_id": "bad"}).status_code == 401
    assert nav.client.get("/memory?session_id=demo-1&limit=101", headers=nav.headers).status_code == 422


def test_unknown_route_and_missing_revision_are_rejected(nav):
    assert nav.start(route="missing").status_code == 404
    nav.check()
    state = nav.start().json()
    response = nav.client.post("/route", headers=nav.headers, json={"session_id": "demo-1", "navigation_id": state["navigation_id"], "action": "confirm", "action_id": "no-revision"})
    assert response.status_code == 422


def test_history_capacity_does_not_prevent_a_valid_stop():
    from stride_backend.settings import Settings
    settings = Settings(_env_file=None, local_dev=True, max_route_actions_per_session=1,
                        session_tokens={"demo-1": "route-ui-token"})
    with navigation_app(settings=settings) as nav:
        nav.check()
        state = nav.start().json()
        assert nav.act("pause", state).status_code == 429
        assert nav.act("stop", state, expected_revision=0).status_code == 409
        assert nav.act("stop", state).json()["state"] == "idle"


def test_known_other_navigation_id_cannot_be_modified(nav):
    nav.check()
    own = nav.start().json()
    other = nav.client.post("/route", headers={"X-Session-Token": "other-ui-token"}, json={"session_id": "other", "route_id": "demo-hallway", "action": "start", "action_id": "other-start"}).json()
    assert nav.act("confirm", own, navigation_id=other["navigation_id"]).status_code == 409
    other_memory = nav.client.get("/memory?session_id=other", headers={"X-Session-Token": "other-ui-token"}).json()
    assert other_memory["navigation"]["confirmed_checkpoint_count"] == 0
