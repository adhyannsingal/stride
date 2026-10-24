# Phase 3 delivery: webcam preview and hardware pending

> Updated by [Phase 4 integration](phase4-integration.md). Device telemetry/commands below were pending at this earlier checkpoint.

2026-10-24. User confirmed the live box window works and hardware has not arrived.
This updates the older Phase 2 plan; it is not a new four-hour countdown.

## Working and verified

- `origin/software` Phase 3 (18f6660) merged into the vision integration branch.
- Real local webcam preview: `scripts/preview_live.py`; user confirmed visible.
  Q/Esc exits, P pauses/releases camera, +/- adjusts diagnostic confidence only.
  No image recording. Do not run a second camera capture concurrently.
- Phase 3 provides SQLite saved routes, explicit checkpoint confirmations,
  idempotent/revision-checked actions, pause/repeat/stop and persistent last-seen
  memory. Restart pauses navigation and invalidates old guidance. It does not
  infer the user's physical position.
- Added opt-in stable-track memory bridge, enabled by
  `STRIDE_RECORD_STABLE_SIGHTINGS=true`. Two observations are required before a
  track is eligible. Only the matching currently published live frame/generation
  reaches the existing validated memory service; per-track cooldown limits writes.
  DB work is separate from inference. No second inference worker or image storage.
- Added named-route import and Phase 3 vision dependency files. Diagnostic HTTP
  benchmarks use a temporary database rather than the user's saved route database.
- 38 vision/integration tests pass, including actual ONNX fixture inference,
  no first-frame memory, stable bus/person sightings at the last confirmed
  checkpoint, cooldown and restart persistence. Fixture observations are labeled
  fixture; this does not demonstrate a physical route or measured accuracy.
- Phase 3 backend regression suite: 185 passed with the actual detector integration
  fixture enabled. One upstream TestClient deprecation warning.

## Run and use saved places

From repository root after README dependency/model setup:

```sh
PYTHONPATH=.:backend_phase3 STRIDE_LOCAL_DEV=true STRIDE_DETECTOR_FACTORY=app.vision.phase2:build_detector STRIDE_RECORD_STABLE_SIGHTINGS=true .venv-phase3/bin/python -m uvicorn stride_backend.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

This machine already has the dependencies in `/tmp/stride-phase2-venv` (the name
predates Phase 3). Preview relaunch:

```sh
PYTHONPATH=. /tmp/stride-phase2-venv/bin/python scripts/preview_live.py
```

Saved places are named landmarks on a manually defined checked route. Last-seen
memory can say an object was observed near the last checkpoint the user confirmed,
with time/source information. It cannot say that object is still there, determine
metric distance, map a building or automatically navigate back to an object.
The standalone preview does not write backend memory.

Copy `qa/routes/example-unchecked.json`, replace every placeholder instruction and
landmark for a real supervised layout, and choose a unique route ID. Import:

```sh
PYTHONPATH=.:backend_phase3 STRIDE_LOCAL_DEV=true .venv-phase3/bin/python scripts/import_saved_route.py /path/to/your-route.json
```

Imports always clear checked/return_checked flags. Duplicate IDs are rejected.
Only AFTER physically verifying the actual route, mark it checked using the same
`STRIDE_DATABASE_PATH`/working directory as the running backend:

```sh
PYTHONPATH=.:backend_phase3 STRIDE_LOCAL_DEV=true .venv-phase3/bin/python -m stride_backend.route_store check YOUR_ROUTE_ID --note 'Actual human verification details here'
```

Do not run that command against placeholder instructions. The default DB is
ignored `data/stride.sqlite3`. Demo routes remain unchecked until verified.

## Exact remaining UI/backend work

Agent 2 frontend branch handoff says do not merge to main; it was not overwritten.
These are handoff tasks, not messages sent or proof those agents have begun them.

- Agent 2: authenticate against the real backend, list
  `GET /routes?session_id=...`, send `POST /route`, render
  `GET /memory?session_id=...`. Every non-start route action needs navigation_id
  and expected_revision, as well as action_id/session_id/action. Use returned
  state_revision. Do not silently fall back to fixture routes/memory.
- Route guidance events use instruction, created_at, expires_at, event_id and
  valid. Normalize to frontend speech text/created_ms/expires_ms only after
  checking validity/expiry/revision. Include haptic_direction separately.
- Agent 2: apply/review `frontend-speech-fixes.patch`, use a user gesture for
  Enable/test audio, test actual iPhone playback and Stop/interrupt behavior.
  Browser SpeechSynthesis uses the available system voice; iOS selects output
  to paired AirPods. No custom voice provider is configured. Physical AirPods
  playback remains unverified.
- Agent 1: finish sensor telemetry/device command/ACK transport and central
  feedback priority, explicit camera producer policy and remote clock freshness.
  Phase 3 has an internal obstacle hook, not a completed sensor HTTP interface.
  Existing firmware cannot yet be claimed compatible end to end with this API.
- Agent 1/2: reachable same-origin HTTPS runtime and a viewer that does not take
  over the camera. Mac preview is a diagnostic, not that hosted phone workflow.
- Agent 3: integration regressions, reviewed labels/held-out scenes for measured
  misses/false positives, then physical bring-up when the parts arrive.

## Remaining time: prioritize a demonstrable slice

| Priority | Owner | Exit evidence |
| --- | --- | --- |
| Now, software block | Agent 1 + 2, Agent 3 regression | Real route/memory UI, same-session camera/viewer, audible iPhone/AirPods phrase, Stop cancels |
| Before live object narration | Agent 1 + 2 | Fresh authorized events, sensor/fault priority, no stale replay or duplicate narration |
| Immediately when hardware arrives | Adhyann + Agent 3 | Sensor-only calibration, then independent local buzzer/motor; real measurements |
| After local sensor works | Agent 1 + 3 | Fresh telemetry and expired/duplicate command handling; then verified W11 upload |
| Final 45 minutes of the actual deadline | All | Freeze features; supervised checked-route rehearsal, evidence/video and honest fallback labels |

Do not wait until the last block to connect the ultrasonic sensor. Prepare the
wiring now, then verify power and divided ECHO before connecting to ESP32 input.
Run sensor-only first: measured targets around 100/60/30 cm, no-echo/disconnect
behavior and offline operation. Add buzzer, then regulated 3 V motor with the
specified driver/diode. Check exact W11 board/pins before flashing its uploader.
The local warning loop must work without Wi-Fi/backend; network integration is a
separate test. No hardware has been flashed, calibrated or physically validated.

Cut optional Gemini, automatic mapping, GPS import and cosmetic work first.
Keep route confirmation, current-source/expiry checks and truthful source labels.
Detection boxes identify supported classes and image position; they do not prove
all obstacles were found or establish a safe turn. Use a supervised demo layout.

## Reproduce software checks

```sh
PYTHONPATH=.:backend_phase3 /tmp/stride-phase2-venv/bin/python -m pytest tests/vision tests/integration -q
cd backend_phase3
PYTHONPATH=..:. STRIDE_INTEGRATION_DETECTOR_FACTORY=app.vision.phase2:build_detector STRIDE_INTEGRATION_JPEG=/Users/adhyannsingal/Documents/outlook/qa/private/bus.jpg /tmp/stride-phase2-venv/bin/python -m pytest -q
```

The real-model tests require the ignored model and explicit private fixture.
Other machines must supply their own fixture path. No images/DBs were committed.
