# STRIDE backend — Phase 3

Manual checked-route navigation and SQLite route memory, added to the existing
Phase 2 application. Source is in `stride_backend/`; Phase 1/2 endpoints and the
Detector protocol/factory remain compatible. No frontend, model, firmware or
physical haptic delivery is included.

## Run and test

Python 3.11+, tested with Python 3.13. No additional third-party dependencies.

```sh
cd ~/Desktop/LeHacks/stride/backend_phase3
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
STRIDE_LOCAL_DEV=true uvicorn stride_backend.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

Run tests in another terminal:

```sh
cd ~/Desktop/LeHacks/stride/backend_phase3
.venv/bin/python -m pytest -q
```

Swagger: `http://127.0.0.1:8000/docs`. Use **one process, one Uvicorn worker and one
replica**: Phase 2 live state remains in memory. Hosting must supply HTTPS,
`STRIDE_LOCAL_DEV=false`, the existing camera token, session-specific UI tokens,
exact allowed frontend origins, and a writable persistent database path.

Verification: **184 passed, 1 skipped**. The skipped test requires the real YOLO
adapter/image; one upstream Starlette/httpx deprecation warning remains.

## SQLite

`STRIDE_DATABASE_PATH` defaults to `data/stride.sqlite3`, relative to the working
directory. Its parent and schema are created during application startup. Existing
rows are retained. Schema version 1 uses non-destructive `CREATE IF NOT EXISTS`;
unknown future versions fail startup rather than being replaced. Fixture loading
is idempotent and never replaces human verification or route instructions.

Every operation uses its own connection, foreign keys enabled, parameterized SQL
and a short transaction. Writes use `BEGIN IMMEDIATE`. Request/database work runs
in a thread pool, including initialization. No ORM, images, authentication secrets
or image blobs are stored. Database files/journals are ignored by Git. Tests use
isolated temporary files. `:memory:` is unsupported because connections are short
lived; use a temporary file for tests.

| Table | Contents |
| --- | --- |
| routes | Names, descriptions, checked/demo flags, human verification note, epoch timestamps |
| checkpoints | Ordered checked instructions/directions, landmarks, separately modeled optional return instructions |
| navigation_sessions | Session ownership, route, state, checkpoint index, confirmed count, revision, timestamps |
| route_events | Ordered state/progress events with unique IDs and timestamps |
| object_sightings | Last-seen metadata, provenance, tracking identity and observation/recording timestamps |
| navigation_heads | Current navigation and monotonically increasing per-session revision |
| route_actions | Persistent idempotency records, including rejected actions |
| guidance_events | Structured cues, revision, checkpoint, expiration and invalidation |

On restart, previously guiding routes become paused and old cues are invalidated.
Confirmed progress survives. Read `/memory`, verify the situation manually, then
explicitly resume the saved navigation. Blocked routes remain blocked; restart
or stale/unknown observations never clear an obstacle condition.

## Authentication and endpoints

All new endpoints use the existing session cookie or `X-Session-Token` and require
`session_id`. Camera credentials do not grant route/memory access. Authorization
is checked on each request, including ownership of navigation IDs. Local auth
bypass is explicit through `STRIDE_LOCAL_DEV=true` with an empty UI-token mapping.
No-cache headers and the existing JSON error envelope are used.

| Endpoint | Contract |
| --- | --- |
| `GET /routes?session_id=...&limit=25` | Available route definitions, including checked/demo flags and checkpoints |
| `POST /route` | Canonical route actions; typed `RouteResponse` |
| `GET /memory?session_id=...&include_events=true&limit=25` | Current/previous progress, confirmed checkpoints, optional event history, last-seen sightings |

History/list limits are 1–100. The route catalog is shared predefined data;
progress/events/sightings are isolated by authenticated session. Memory never
claims that a remembered object is currently visible or that the user's current
physical position is known. Existing `/health`, `/time`, `/frame`, `/auth/session`,
`/vision`, `/vision/latest` and `/status` remain available.

For protected scripts add `-H "X-Session-Token: $STRIDE_SESSION_TOKEN"` to the
examples below. Browsers should exchange their provisioned session credential at
`POST /auth/session`, then send the existing HttpOnly cookie with
`credentials: "include"`. Never put the camera token into frontend JavaScript.

## Demo fixtures and human verification

Startup installs **unchecked** `demo-hallway` (A → B → C) and `demo-tabletop`
(two controlled markers), unless `STRIDE_LOAD_DEMO_ROUTES=false`. They describe
no verified real building. Both retain `demo_fixture=true` even after the team
checks its actual supervised layout. Unchecked routes return 409 when started.

Inspect every instruction against the actual layout first. Only after human
verification, mark a route checked through the local CLI:

```sh
STRIDE_LOCAL_DEV=true python -m stride_backend.route_store check demo-hallway \
  --note 'Verified by <person>, <date>, against the actual supervised demo layout'
```

This changes the database checked flag and records the human note; it does not
validate physical safety. There is no remote route-editing/admin API. Internal
`RouteCatalog.add_route(SavedRoute(...))` supports checked team-supplied definitions.
Return instructions/directions and their checked flag are separate fields;
navigation uses only forward instructions. No reverse route is generated.

## Route controls and examples

```sh
curl 'http://127.0.0.1:8000/routes?session_id=demo-1'
curl http://127.0.0.1:8000/route \
  -H 'Content-Type: application/json' \
  --data '{"session_id":"demo-1","route_id":"demo-hallway","action":"start","action_id":"nav-001"}'
```

Example response from a temporary test database, whose route was marked checked
only for the example. IDs and timestamps vary in a running application:

```json
{
  "session_id": "demo-1",
  "navigation_id": "904403f5-496d-4a47-befa-2254440f9175",
  "route_id": "demo-hallway",
  "state": "guiding",
  "state_revision": 1,
  "current_checkpoint": {"checkpoint_id":"demo-hallway:A","ordinal":0,"landmark":"Demo marker A"},
  "confirmed_checkpoint_count": 0,
  "total_checkpoints": 3,
  "confirmed_checkpoints": [],
  "instruction": "Proceed to checkpoint A.",
  "haptic_direction": "straight",
  "guidance_event_id": "0efe7618-3aff-4fba-9c52-c9b4cd9d2c8a",
  "guidance_event": {
    "event_id": "0efe7618-3aff-4fba-9c52-c9b4cd9d2c8a",
    "navigation_id": "904403f5-496d-4a47-befa-2254440f9175",
    "session_id": "demo-1",
    "instruction": "Proceed to checkpoint A.",
    "direction": "straight",
    "created_at": 1792863103558,
    "expires_at": 1792863113558,
    "state_revision": 1,
    "checkpoint_id": "demo-hallway:A",
    "valid": true
  },
  "status_message": "Follow the checked instruction and explicitly confirm the checkpoint. Physical position is not known.",
  "physical_position_known": false,
  "progress_source": "user_confirmation",
  "created_at": 1792863103558,
  "updated_at": 1792863103558,
  "action_id": "nav-001",
  "duplicate": false,
  "applied_revision": 1
}
```

Use the returned navigation ID and revision for the next action:

```sh
curl http://127.0.0.1:8000/route \
  -H 'Content-Type: application/json' \
  --data '{"session_id":"demo-1","navigation_id":"904403f5-496d-4a47-befa-2254440f9175","expected_revision":1,"action":"confirm","action_id":"nav-002"}'
curl 'http://127.0.0.1:8000/memory?session_id=demo-1&include_events=true&limit=25'
```

That confirm returns revision 2, confirmed count 1, checkpoint B, instruction
`Turn left at checkpoint B.`, and a new valid left-direction guidance event.
The memory response contains `session_id`, `routes`, `navigation`,
`previous_navigation`, `route_events`, `sightings`, and `returned_at`.
`route_models.py` and `/docs` define all fields, including complete last-seen data.

| State | Actions | Effect |
| --- | --- | --- |
| No navigation / idle | start | New checked-route navigation, first instruction |
| guiding | confirm | Confirm exactly one checkpoint; next instruction or completed |
| guiding | repeat | New explicit cue for the same instruction; no state/revision/progress change or duplicate progress event |
| guiding | pause | Paused with progress retained; old cue invalidated |
| paused | resume | Guiding at the same unconfirmed checkpoint; new cue |
| guiding / paused / blocked / completed | stop | Idle, preserving history and confirmed progress |
| completed | start | New navigation with a new ID and current expected revision |
| blocked | stop only | No confirm, repeat, resume or normal turn instruction |

Three checkpoints require **three confirmations**, including the last stop
checkpoint. Invalid transitions return 409. Every non-start action requires
`navigation_id` and `expected_revision`; stale/missing identities cannot operate
on a later navigation. Starting again after an earlier navigation also requires
the latest expected revision. Revisions increase across navigations for a session.
Simultaneous confirms using one revision cannot advance twice.

Retry identical `action_id` requests without duplicate progression. Reusing an ID
with different contents returns 409. Duplicate successes return the **current**
authoritative navigation and `duplicate=true`, with their original
`applied_revision`; they never recreate an old instruction event. Rejected actions
are remembered. History is bounded by `STRIDE_MAX_ROUTE_ACTIONS_PER_SESSION`, with
one reserved successful stop record; it is never silently evicted to permit replay.

Blocking has only an internal unit-tested seam:
`NavigationController.apply_obstacle(..., ObstacleObservation(...))`. Fresh valid
obstacle input blocks; only fresh valid clear input changes blocked to paused,
then a human explicitly resumes. Unknown/stale observations leave it blocked.
No physical telemetry is connected in Phase 3.

## Frontend guidance handling

Speak only a valid, unexpired `guidance_event` for the current navigation/revision.
Deduplicate by event ID; repeated `/memory` reads never create cues. Check validity
and expiration again at playback. Pause, stop, completion, blocking and restart
invalidate old cues; discard queued output when state/revision changes. An
explicit repeat produces a new cue ID but never confirms a checkpoint.
`haptic_direction` is intended metadata only; no vibration command is delivered.
`physical_position_known` is always false. A confirmed checkpoint is recorded
user progress, not automatic localization. Route and vision stops are independent.

## YOLO-to-memory integration

The detector protocol and `STRIDE_DETECTOR_FACTORY=module:factory` mechanism are
unchanged. No extra inference pipeline or model dependencies are introduced.
Sightings are opt-in confirmed-track events, **not every object on every frame**:

```python
batch = app.state.frame_store.latest_detections(session_id)
if batch is not None:
    outcome = await app.state.memory.record_sightings(
        session_id=session_id,
        batch=batch,
        track_ids=("stable-track-id-confirmed-by-the-tracking-integration",),
    )
```

The vision integration chooses tracks it has actually stabilized. The hook
accepts 1–16 distinct IDs, validates the current fresh batch/session/receipt,
frame/device/source metadata and selected detections, and associates the latest
checkpoint explicitly confirmed by the observation's server receipt time.
No change to the teammate's `detect(frame) -> DetectionBatch` is needed. The hook
is exposed now; automatic track-confirmation policy remains with that teammate.

Repeated observations of a stable tracked object are deduplicated, with a default
30-second update cooldown. Keys include device/boot/source revision, vision
generation and an application-instance namespace so restarted tracking IDs cannot
merge old identities. Storage is capped at 200 sightings per session by default.
Fixture/simulated provenance is preserved, never relabeled real. DB write failure
returns `error="memory_unavailable"` without crashing the live worker.

All recall records say `observation=last_seen`. They include age, track/frame,
source/provider, checkpoint association and original timestamps. Because camera
clock alignment is not yet verified, `captured_at` is null, original camera
`captured_ms` is preserved, and `last_seen_at`/age use the original server receipt
with `timestamp_basis=server_receipt`. Recording/recall time does not reset age.
Checkpoint association means **last user-confirmed checkpoint**, not measured
object/user position. No Gemini implementation is included.

## Limits and remaining gates

Actual human route verification is required before guidance. These fixtures are
not validated for independent navigation. Physical obstacles, haptics, actual
YOLO, hosted deployment and W11/AirPods behavior are unverified. Existing live
vision targets (5 fresh results/s, capture-to-result p95 <=500 ms, age <=1 s) remain
separate measurement gates; no throughput is claimed from test doubles.

Use persistent local storage on the chosen host; do not run multiple replicas
with the in-memory Phase 2 controller. Back up route history as appropriate.
In this agent environment socket binding is restricted; in-process HTTP tests
exercise startup, SQLite and endpoints. Run the launch command in a normal
terminal for the network smoke test. Raw images and credentials are never stored.
