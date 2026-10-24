# Stride API contract

> **Current architecture:** continuous automatic perception is P0. Read [LIVE_VISION.md](../Stride_Live_Vision_Requirements.md) first; it defines the mandatory live loop and its acceptance gates. Hosted YOLO handles the live loop; Gemini is optional enrichment. Implementation and physical validation remain to be completed by the team.

**Normative for all three agents.** Current ownership: Agent 1 backend (including server device policy), Agent 2 frontend, Agent 3 hardware/firmware/live vision. The three separate agent briefs supersede older numbering. JSON keys are snake_case. UTC wall times use integer Unix milliseconds (`*_ms`). Durations are nonnegative integer milliseconds. IDs are UUID strings unless a device ID/boot ID is explicitly named. Any retry of a mutating action reuses its `action_id`. No raw secrets appear in responses.

## Common rules

- Same-origin HTTPS web app. `/auth` verifies `APP_ACCESS_CODE`, sets the secure HttpOnly/SameSite auth cookie; `/health` is public. UI APIs require cookie auth; device APIs require their device bearer token and a bound active session. `/auth` is rate-limited.
- `source`: `real | simulated | fixture`, server-derived. `origin`: `browser_camera | w11_camera | devkit | simulator | fixture`, server-derived from authenticated adapter. These are distinct fields; do not collapse them into one inconsistent enum.
- Simulator routes exist only with `ALLOW_SIMULATION=true`; use a distinct simulated session. A simulated session never sends commands to a physical device. Real/fixture perception cannot be mixed silently.
- `/sessions` creates a session with `mode=training | hardware_navigation`, camera origin and optional bound device IDs. A person confirms which physical devices belong to that session. Firmware config uses its issued session ID.
- Responses include server time and state sequence. `/status` is authoritative; frontend ignores responses with lower `state_seq`. Event IDs are stable across polling.
- Limits: JPEG ≤1,000,000 bytes; longest side ≤1920 px and total pixels ≤1920×1080 in either orientation; 640×480 preferred; labels ≤100 chars; target ≤80; route ≤20 steps; image/task descriptions are data. Server rejects malformed images and nonfinite numbers.
- Error body: `{"error":{"code":"DEVICE_UNAVAILABLE","message":"Feedback device is disconnected.","retryable":true},"request_id":"uuid"}`. Schemas and HTTP status are covered in the main spec.

## Auth, sessions and route definition

| Method/path | Request | Response |
| --- | --- | --- |
| `GET /health` | None | Readiness, version/commit, configured-provider boolean; no secret values. |
| `POST /auth` | `{ "access_code": "user-entered-value" }` | `200 {"authenticated":true}` and cookie; reject incorrect code. |
| `POST /sessions` | `action_id`, `mode`, `camera_origin`, optional `camera_device_id`/`feedback_device_id` | Session ID, mode, source, command generation, device bindings, `state_seq`, `server_time_ms`. |
| `POST /sessions/{id}/devices` | `action_id`, optional camera/feedback device IDs | Current bindings. Cannot bind a device already used by another active session. |
| `POST /sessions/{id}/camera` | `action_id`, `camera_origin` | Source revision + selected origin; invalidate older-source perception. |
| `GET /time` | Auth cookie or device token | `{ "server_time_ms": 123 }`; used with RTT to establish clock offset. |
| `POST /routes` | `action_id`, name, ordered steps, separate optional return route | Stored route. Validate unique checkpoint IDs, nonempty instructions and allowed patterns. |
| `GET /routes` | Auth | Available saved routes; sample route marked `is_demo=true`. |

Route example:

```json
{
  "action_id": "00000000-0000-4000-8000-000000000001",
  "name": "Checked demo route",
  "is_demo": true,
  "steps": [
    {"checkpoint_id":"A","instruction":"At the marked start, turn left toward checkpoint B.","pattern":"left"},
    {"checkpoint_id":"B","instruction":"At checkpoint B, turn right toward checkpoint C.","pattern":"right"},
    {"checkpoint_id":"C","instruction":"Checkpoint C reached. Route complete.","pattern":"stop"}
  ],
  "return_steps": []
}
```

This example is a schema fixture, not directions through the user's actual environment. Only physically checked instructions are marked ready for the real demo.

`POST /route` request: `action_id`, `session_id`, `action=start|confirm|repeat|pause|resume|stop`, `route_id` for start. Returns authoritative route state with route ID, checkpoint index/ID, instruction, pattern, action/event IDs and overlay. `confirm` while paused/blocked/unknown in hardware mode returns 409 without advancing. Duplicate action returns the same result. Final confirmation completes once. `repeat` emits a fresh repeat event once per action ID without changing the checkpoint index.

## Frame ingestion

`POST /frame` with `Content-Type: image/jpeg`, body raw bytes. Browser uses the auth cookie; W11 uses `Authorization: Bearer CAMERA_DEVICE_TOKEN`.

Required headers: `X-Session-Id`, `X-Device-Id`, `X-Boot-Id`, `X-Frame-Id`, `X-Sequence` (integer), `X-Captured-Ms` (aligned epoch), `X-Clock-Synced` (`true|false`), `X-Source-Revision` (current server-issued revision). Camera origin is inferred from adapter credentials/session, not trusted from a client-controlled real/simulated flag.

Response 201: `frame_id`, `origin`, `source`, `source_revision`, `captured_ms`, `received_ms`, `clock_synced`, dimensions and `server_time_ms`. Duplicate `(session,device,boot,sequence)` with same frame returns the existing frame; conflicting duplicate is 409. Out-of-order latest-frame updates cannot replace a newer frame. Clear old frame buffers on source/session change; retain only a bounded latest/current snapshot needed by the active request. Reject when device binding is wrong or `X-Source-Revision` is not current. Late uploads from the retired selection cannot become new-source frames.

## Perception

`POST /perception`:

```json
{
  "action_id": "00000000-0000-4000-8000-000000000002",
  "session_id": "00000000-0000-4000-8000-000000000010",
  "frame_id": "00000000-0000-4000-8000-000000000020",
  "task": "find",
  "target": "mug"
}
```

Response fields: `observation_id`, `status=ok|not_found|expired`, `origin`, `source`, `provider=gemini|fixture`, `frame_id`, `source_revision`, `captured_ms`, `completed_ms`, `age_ms`, `latency_ms`, validated objects, `speakable`, and optional `speech_event`. `objects` contain label, normalized box and software-computed position. `speakable` is true only for a current eligible result with no higher-priority condition. Busy returns 409; real provider errors return 503/504 or 429. Never return a fixture as a real provider success.

For expired/mismatched results set `speakable=false` and `objects=[]` in the live result; retain diagnostic metadata only. Provider may return `{objects:[]}`; that is not-found, not a network error. A sighting is stored only after validated eligible real/explicitly simulated observation, with capture timestamp and last-confirmed checkpoint association. No object-distance field exists.

## Telemetry and status

`POST /telemetry` uses the feedback token. Simulator uses its own authenticated developer route `POST /simulation/telemetry` with the same structural payload and server-enforced simulated source.

```json
{
  "session_id": "00000000-0000-4000-8000-000000000010",
  "device_id": "feedback-1",
  "boot_id": "boot-unique-per-restart",
  "sequence": 21,
  "uptime_ms": 30200,
  "distance_cm": 45.0,
  "valid": true,
  "local_alert": "warning",
  "active_command_id": null
}
```

Allowed `local_alert`: `none|warning|urgent|sensor_fault`. Invalid reading uses `distance_cm=null, valid=false`. Reject NaN/Infinity/negative values. Derive backend warning from validated range/freshness; do not blindly trust local_alert. Received time is server-assigned. Duplicate sequence is idempotent; older same-boot sequence ignored/rejected. New boot flushes previous device commands and resets sequence expectations. A delayed packet from a retired boot cannot become current.

Response: accepted sequence, server time and current device-command generation.

`GET /status?session_id=...`:

```json
{
  "session_id": "00000000-0000-4000-8000-000000000010",
  "state_seq": 42,
  "server_time_ms": 1790000000000,
  "mode": "training",
  "route": {"state":"guiding","checkpoint_index":0,"checkpoint_id":"A","overlay":"none"},
  "camera": {"origin":"browser_camera","source":"real","connected":true,"age_ms":200},
  "feedback": {"origin":"simulator","source":"simulated","connected":true,"valid":true,"distance_cm":120,"age_ms":100,"alert":"none","ack_state":"unavailable"},
  "perception": {"provider":"gemini","available":true,"busy":false,"latest":null},
  "speech_event": null,
  "haptic_event": null,
  "memory": {"durability":"local_sqlite","export_available":true}
}
```

Camera latest-frame age is not proof the camera is disconnected; expose source/device heartbeat separately as implementation needs. `age_ms` measures the specific sample/event. `connected=false` or stale feedback implies `valid=false` for navigation even if the last numeric distance remains in the diagnostic log. `speech_event` has UUID, kind, priority, text, created/expires times; the UI speaks each event once, discards expired events, and checks priority again before playback.

## Direction commands and acknowledgments

`GET /devices/{device_id}/commands?session_id=...&boot_id=...` requires feedback token and current binding/boot. Returns `command:null` or:

```json
{
  "command": {
    "command_id": "00000000-0000-4000-8000-000000000030",
    "session_id": "00000000-0000-4000-8000-000000000010",
    "generation": "00000000-0000-4000-8000-000000000040",
    "device_boot_id": "boot-unique-per-restart",
    "pattern": "left",
    "priority": "route",
    "remaining_ttl_ms": 1100
  },
  "server_time_ms": 1790000000000
}
```

Queue lifetime is at most 1500 ms from server creation. If not accepted before expiry, mark expired and do not replay. Server returns remaining TTL at dispatch, not a new 1500 ms on every poll. Firmware subtracts its measured HTTP request elapsed time conservatively before starting; reject if remaining window is exhausted. Never compare an ESP32 monotonic clock directly to server epoch. Max motor pulse/pattern duration is firmware-bounded separately.

Firmware validates command generation/boot binding, checks ID deduplication, then sends `POST /devices/{id}/ack` with session ID, boot ID, command ID, generation and status `accepted|completed|rejected|expired`, optional short reason. A duplicate ACK does not execute again. Poll may redeliver the same ID until acceptance/expiry; the motor runs once. At most one pending remote route cue exists per device; new route action replaces/cancels old cue. Local obstacle never waits for a command.

Simulator command polling/ACK uses `POST /simulation/ack` and the developer session. A simulated ACK cannot mark a physical device command complete. Status includes a simulated haptic event for UI preview without any hardware-delivery claim.

## Memory

`GET /memory?session_id=...&kind=routes|sightings|events&limit=20` returns timestamped records with source/age and checkpoint association. Default sighting recall filters out simulated/fixture records for real sessions. `GET /memory/export?session_id=...` returns a JSON export of that session and its saved route. `POST /memory/import` accepts validated exported route definitions only; do not import pending commands or fake old live telemetry.

## Optional route import

Only if P0 passes: `POST /routes/import-walking` with action ID, origin `[lon,lat]`, destination `[lon,lat]`, destination name. Backend calls Mapbox with walking profile and steps, normalizes route instructions/patterns, records `route_source=mapbox` and preserves provider attribution. Explicit checkpoint confirmation remains. Missing provider returns unavailable; never generate plausible-looking substitute directions.

## Python integration seam: backend and vision

Agent 1 owns all `app/devices/`, auth, DB, schemas, `/frame`, `/status`, deployment and application assembly. Agent 2 owns all `web/` and speech playback. Agent 3 owns `app/vision/`, all firmware, device simulation clients and model/performance tests. There is no separately owned server-side FeedbackService to mount from another agent.

Agent 1 supplies `app.dependencies.require_ui_auth`, `require_device_auth` and `app.state` canonical session/feedback/event services. Auth dependencies verify role/device/binding rather than trusting payload IDs. Agent 3 supplies `app.vision.router.router` and `VisionService(settings)` with async lifecycle `start()/close()`, quick `offer_frame(frame)`, `control(session_id, action, source_revision)`, `snapshot(session_id, now_ms)` and `invalidate(session_id, source_revision)`. Freeze exact sync/async signatures and canonical DTO names before implementation; lifecycle/control callbacks must not block the event loop.

Agent 1 creates one `app.state.vision` in lifespan and mounts the router once. `/frame` validates and offers eligible JPEG bytes with canonical identity/provenance/revision/time metadata to that instance. Agent 3 owns newest-frame concurrency, inference and track stabilization. An injected async observation callback delivers eligible results to Agent 1's sighting persistence/event arbiter; it must not block inference on slow persistence. Agent 1 controls shared route/feedback state and final speech events. Agent 2 deduplicates/plays those events; it does not derive competing speech from raw boxes.

The router uses Agent 1's shared auth and schemas. `POST /vision` receives `action_id`, `session_id`, `action=start|pause|resume|stop`; action idempotency is enforced at the API boundary. Camera revision and session membership are server-authoritative. Pause/source/session change invalidates pending/in-flight output before publication. Backend handles route pause/stop propagation to the same instance. No second frame endpoint/model/DB/command queue.

### Device-authorized camera state

Agent 1 implements `GET /devices/{device_id}/camera-state?session_id=...` with camera-role bearer token, device/session binding checks and response fields `session_id`, `device_id`, `selected`, `active`, `source_revision`, `state_seq`, `server_time_ms`. `active` reflects current live state; selected=false means this device must not supply the active camera. W11 polls before and during automatic uploads, pauses on inactive/unreachable state, and attaches the current revision to each frame. The UI receives the same revision from camera selection/control responses. Never require W11 to use a browser cookie.

## Live detector contract

The mandatory `/vision` and `/vision/latest` endpoints, automatic frame-worker linkage, detector scores/track IDs and stricter 1000 ms live-result cutoff are defined in `../Stride_Live_Vision_Requirements.md`. They supersede any interpretation that `/perception` button requests are the primary walking-vision loop. Keep `/perception` for optional Gemini snapshots only.

### Canonical boxes and live output example

Optional Gemini raw provider payloads (including `box_2d` fixtures) are internal adapter inputs, not the published detector/object schema. Convert them to the canonical box representation after validating actual provider ordering/scale; never expose two conflicting meanings of normalized coordinates.

`objects[].box` is `[x_min,y_min,x_max,y_max]` normalized to `[0,1]` in the upright decoded camera image, with min < max. IDs, labels and scores derive from the selected detector/tracker; score is not a safety probability. The server computes image-relative position from the box.

```json
{
  "session_id":"00000000-0000-4000-8000-000000000010",
  "state_seq":43,
  "server_time_ms":1790000000350,
  "frame_id":"00000000-0000-4000-8000-000000000020",
  "captured_ms":1790000000100,
  "completed_ms":1790000000300,
  "age_ms":250,
  "source_revision":1,
  "origin":"browser_camera",
  "source":"real",
  "status":"live",
  "provider":"yolo",
  "result_hz":5.0,
  "objects":[{"track_id":"track-1","label":"chair","score":0.83,"box":[0.1,0.2,0.4,0.9],"position":"left"}],
  "speech_event":null
}
```

This is a schema example, not measured performance. Backend decorates latest results with its authorized event; `/status` and latest reuse the same event IDs. Agent 3 never bypasses backend priority. A live frame with age >1000 ms or unverifiable clock/source cannot produce current-scene speech; return no current objects when stale. The UI rechecks age/revision/expiry/priority at playback. Model candidate stabilization (two consistent detections, 3 s per-track/position cooldown) belongs to Agent 3; server arbitration belongs to Agent 1; playback belongs to Agent 2.

`source_revision` is a monotonic integer per session. A camera selection change increments it. Vision controls echo it; retired revisions cannot offer/publish. All mutating controls carry an idempotent action ID. The frontend sends the new `X-Source-Revision` header and firmware fetches it from camera-state. Agent 1 updates shared examples/OpenAPI before any implementation renames these fields.

## Multiple browser clients: explicit capture ownership

Mac webcam capture and iPhone viewer/audio share one session. Viewing/joining/polling is side-effect free: no automatic source selection, camera access or session replacement. `POST /sessions/{id}/camera` accepts `action_id`, `camera_origin` and the selected `camera_device_id`; for browser source this ID denotes the registered capture producer, not the viewing phone. Selection atomically binds that producer and increments `source_revision` on change. `/status.camera` includes selected `device_id` and `source_revision`. Only its authenticated/bound current-revision frames are accepted as active. Viewer clients never upload merely because origin is browser_camera.

The frontend uses a manual existing session ID to join; normal UI authentication is still required. A viewer's page hide cancels its local polling/speech only. Explicit session Pause/Stop remains global. Capture-client hide pauses its capture and requests backend pause; if that request cannot arrive, normal freshness expiry suppresses old output. W11 remains an explicit later source selection. This adds no new device token exposure or peer-to-peer camera connection.
