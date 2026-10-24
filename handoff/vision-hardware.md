# Agent 3 — vision and hardware handoff

Branch `stride/hardware-vision`, based on main `85d445f`. This handoff is included
in the Agent 3 commit; run `git log -1 --oneline` for its exact SHA. Shared backend,
contracts, frontend and deployment files were not rewritten. The original local
work and extracted old handoff are preserved. The updated ZIP was extracted to
`handoff/current-package/` locally so obsolete role files were not overwritten.

## Ready now

- Real YOLOv8n/ONNX detector, canonical `[xmin,ymin,xmax,ymax]` float boxes 0..1.
- Load-once, newest-frame inference; one pending frame/session, one model job
  globally, max eight sessions. CPU work runs off the FastAPI event loop.
- Stable tracks/two observations/3 s position cooldown; candidate callback only.
- Pause/stop/source retirement invalidation; 1000 ms freshness gate at offer,
  completion, callback dispatch and snapshot. No old output becomes current.
- Exported FastAPI router that fails closed until Agent 1 supplies its API bridge.
- DevKit sensor/local feedback + separate bounded network task; compiled.
- W11 automatic uploader with board-verification gate; syntax-only compiled.
- API simulator restricted to simulation routes, plus real-API webcam smoke client.
- 19 Python tests, native C++ controller checks, export parity and measured webcam.

## Exact install/model/test commands

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r app/vision/requirements-dev.txt
PYTHONPATH=. .venv/bin/python scripts/export_model.py
.venv/bin/python -m pytest tests/vision tests/integration -q
clang++ -std=c++17 -Wall -Wextra -Werror tests/vision/controller_test.cpp -o /tmp/stride-controller-test
/tmp/stride-controller-test
PYTHONPATH=. .venv/bin/python scripts/measure_live.py --seconds 60 --output qa/agent3-webcam.json
ARDUINO_CLI=/tmp/stride-arduino/arduino-cli firmware/check.sh
```

No root app/main.py exists in this branch; Agent 1 supplies the application.
`app/vision/requirements-runtime.txt` contains the serving dependency request:
FastAPI 0.162.0, NumPy 2.4.6, Pillow 13.0.0, ONNX Runtime 1.31.0. Agent 1 alone
incorporates compatible versions into requirements.txt. Torch/Ultralytics/ONNX
conversion/OpenCV are development-only; do not deploy the conversion stack.

`models/manifest.json` records checkpoint source/hash, ONNX hash, exact 80 labels,
versions/input/decoder/NMS. Model file is `models/yolov8n.onnx`, approximately
12.1 MiB. CPU provider, two inference threads, static input [1,3,320,320], output
[1,84,2100], RGB letterbox 114, confidence .35, class-aware NMS .45. No mirroring.
Optional Gemini provider inputs must separately convert to the same XYXY schema.

Checkpoint download is pinned to the official assets v8.4.0 URL and verified by
SHA256 before loading. Re-export writes a fresh artifact hash (export metadata can
change it); deploy the matching model/manifest pair. Model binaries are not in Git.
Ultralytics upstream is AGPL-3.0; retain upstream attribution/license requirements,
not an assumption of unrestricted model redistribution. License source:
https://github.com/ultralytics/ultralytics/blob/main/LICENSE .

## Agent 1 integration request — one instance, no competing controller

Settings consumed: `LIVE_DETECTOR_MODEL_PATH=./models/yolov8n.onnx` and optional
`LIVE_DETECTOR_MODEL_SHA256` matching manifest. The checksum is verified if supplied.
No new shared settings file is supplied here; Agent 1 is the sole writer.

```python
from app.vision.service import VisionService
from app.vision.router import router

vision = VisionService(settings, on_observation=handle_observation)
await vision.start()
app.state.vision = vision
app.state.vision_api = CanonicalVisionAPI(...)  # Agent 1 supplies this bridge
app.include_router(router)
# await vision.close() at shutdown
```

Exact sync methods:

- `bind(session_id, revision, source, origin)`: after canonical session binding;
  rebind only with increased revision; pauses/invalidate old source.
- `control(session_id, action, source_revision) -> dict`: canonical API owns UUID
  action-ID idempotency BEFORE calling. Repeating raw service control resets the
  generation; do not call it twice for a retried API action.
- `offer_frame(Frame(...)) -> None`: nonblocking, after canonical `/frame` validates
  auth/binding, JPEG, boot/sequence/dedup, selected source/revision and clock.
- `snapshot(session_id, now_ms=None) -> dict`: recomputes age; no final speech or
  independent global state_seq. Backend adds authoritative sequence/events.
- `invalidate(session_id, source_revision)`: cancels pending/current/tracks and
  callback work; retired in-flight results cannot publish. Pauses processing.
- `is_current(observation, now_ms=None) -> bool`: backend callback rechecks directly
  before persistence/event creation, and checks its own current priority/session.

Async `start()/close()`. close waits up to 2 s then cancels async jobs; Python
threads cannot forcibly terminate a stuck native inference call. Closed service
cannot accept/publish new work. No new processes/inference backlog are spawned.

Internal immutable `Frame` fields: session_id, device_id, boot_id, sequence,
frame_id, captured_ms, source_revision, source, origin, jpeg, clock_synced, width,
height, received_ms. Identity/provenance are server-authorized. Duplicate canonical
uploads MUST NOT offer twice (would falsely count two consistent observations).

`handle_observation(dict)` is async. Payload has source/frame/boot/sequence/time,
vision_generation, objects, optional candidate_event. Queue retains one newest
observation/session, callback bounded at 250 ms; slow persistence never blocks
inference. A callback may lose a candidate under overload; it must never publish
an expired/retired one. Callback and model exception text never leaks to API.
Backend converts candidate events to final authorized events and persists eligible
sightings. Service/router never bypass obstacle/fault/route priority.

`CanonicalVisionAPI` is the requested bridge implementing two async methods:
`control(request, vision)` and `latest(request, vision)`. The router delegates
only to this injected instance and otherwise returns 503. Agent 1's bridge:

1. Uses canonical require_ui_auth, shared request schemas and session ownership.
2. Validates/deduplicates POST action_id, reads server revision, calls control once.
3. Calls snapshot for GET and decorates both with the SAME shared state_seq and
   centrally authorized unexpired speech_event used by `/status`.
4. Generates a deduplicated unavailable fault when active fresh results disappear;
   suppresses observations under obstacle/fault/route priority.
5. Uses existing shared structured-error handlers. Do not silently serve this as
   an unauthenticated router or expose raw candidate events as playback events.

This bridge is an explicit small mounting request, not a replacement auth/schema
implementation. The fixture bridge in tests/integration demonstrates the seam;
actual Agent 1 integration remains untested until its app is pushed.

## Agent 2 consumer notes

Canonical `objects[].box` is XYXY floats 0..1, image-relative position only.
Only play centrally decorated speech_event once by ID; recheck current revision,
age <1000 ms, expiry and priority at playback. Pause/hide/offline cancels capture,
output and old requests; explicit resume. Start once drives automatic uploads.
Use server-issued X-Source-Revision on every frame. W11 selection stops browser
uploads; device firmware polls its own authorized camera-state endpoint.

## Firmware/API smoke

Full tool/configuration/physical sequence: firmware/README.md.
Firmware uses the canonical camera-state response in contracts/examples.json and
all upload headers including X-Source-Revision. Telemetry generation response is
accepted as `generation` or `command_generation`; Agent 1 must confirm the chosen
name. Simulated haptic events need command_id, generation and remaining_ttl_ms for
simulation ACK; absent fields are reported as an integration gap, never invented.

Privately set STRIDE_UI_COOKIE for a real logged-in or developer simulation session.
Do not pass tokens in command-line arguments. Once Agent 1 publishes its backend:

```sh
PYTHONPATH=. .venv/bin/python scripts/live_smoke.py --base-url https://HOST --session-id UUID --device-id BOUND_CAMERA_ID --output qa/hosted-smoke.json
PYTHONPATH=. .venv/bin/python scripts/simulate_feedback.py --base-url https://HOST --session-id SIMULATED_UUID --scenario demo
# Other scenarios: clear, warning, urgent, invalid, stale, reboot, ack-delay
```

Simulator completion is labeled simulated, never physical. No physical telemetry
or command endpoint is called by simulator. The existing backend must enable and
authorize simulation; no alternate backend or mocked production response is added.

## Current blockers and immediate next steps

1. Agent 1 app/bridge + actual same-origin deployed URL/access. No hosting code or
   cloud account setup belongs to Agent 3. Run actual /frame + /vision smoke next.
2. Human deadline still unknown; no new six-hour clock was assumed.
3. W11 exact PCB/vendor GPIOs/flash/PSRAM/boot settings, real device and parts.
   No USB board identified by Arduino CLI. Syntax-only proof cannot unlock it.
4. Actual iPhone/AirPods, sensor/motor/offline/power/thermal/15-minute checks.
5. Controlled moved/new/removed object coverage and misses; 60-second throughput
   alone does not complete L01 or prove hazard coverage.

Evidence: qa/vision-hardware.md. Existing historical failed runs are preserved.
No deployment, push, physical flash, account purchase or external messages claimed.
