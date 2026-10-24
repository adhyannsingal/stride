# STRIDE backend — Phase 2

**Merged backend/vision setup:** the real detector plugin is now
`app.vision.phase2:build_detector`. Start from the repository root using the
[combined instructions](../handoff/backend-vision-integration.md) or
[root README](../README.md). They install the serving-only vision dependencies
and keep both repository root and backend_phase2 on PYTHONPATH. The standalone
instructions below can still run without a detector; they do not load a model
merely by starting this backend.

FastAPI frame ingestion and continuous inference orchestration. The YOLO model,
tracking, UI/audio and firmware are supplied by teammates. No model or fake
provider is bundled. One process and **one Uvicorn worker/replica** are required.

## Start and test

Python 3.11+, tested with Python 3.13. Existing `.venv` remains usable; no new
third-party dependencies were added in Phase 2.

```sh
cd backend_phase2  # from repository root
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
# Configure STRIDE_* environment values privately; no .env.example is bundled.
```

For local development only:

```sh
STRIDE_LOCAL_DEV=true uvicorn stride_backend.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
python -m pytest -q
```

Swagger: `http://127.0.0.1:8000/docs`. Without a detector, controls work and vision
reports `unavailable`, never `live`. Local development bypasses session auth only
when `STRIDE_SESSION_TOKENS` is empty; a configured camera token is still required
for device uploads. To use session credentials locally, configure the mapping.

For hosting, set `STRIDE_LOCAL_DEV=false`, a secret `STRIDE_DEVICE_TOKEN`, a JSON
`STRIDE_SESSION_TOKENS` mapping of session IDs to unique random secrets, and exact
`STRIDE_FRONTEND_ORIGINS` in the host environment. Set `STRIDE_DETECTOR_FACTORY`
when the adapter is available. Keep secrets out of Git and frontend builds.

```sh
uvicorn stride_backend.main:create_app --factory --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
```

Use HTTPS ingress. Camera-token absence prevents production startup. Missing UI
credentials return 503 on protected vision routes. A missing/broken detector
leaves HTTP available with `detector_configured=false` and an honest status.

## Endpoints and frontend authorization

| Method/path | Behavior |
| --- | --- |
| `GET /health` | Unchanged Phase 1 health response |
| `GET /time` | Unchanged `{"server_ms": <epoch ms>}` |
| `POST /frame` | Unchanged multipart schema and 202 receipt; automatic dispatch while active |
| `POST /auth/session` | Exchange a session-specific secret for an HttpOnly session cookie |
| `POST /vision` | Apply idempotent session controls |
| `GET /vision/latest?session_id=...` | Current session state and fresh objects, or empty output |
| `GET /status?session_id=...` | `{"backend":{"status":"ok"},"vision":<latest response>}` |

Provision the UI session secret out of band to the authorized user, not in built
JavaScript. Exchange it once; it is distinct from the camera device token:

```sh
curl -c /tmp/stride-cookie.jar http://127.0.0.1:8000/auth/session \
  -H 'Content-Type: application/json' \
  --data '{"session_id":"demo-1","session_token":"<provisioned UI secret>"}'
```

Returns `{"session_id":"demo-1","expires_ms":<server epoch ms>}`. Cookies are
HMAC-signed, HttpOnly, SameSite=Strict, Secure in hosted mode and expire server-side
(default one hour). Rotating the session secret invalidates its cookies. Use
`credentials: "include"` in browser requests. Prefer the same origin/site for UI
and API; cross-site cookie deployment needs a separate reviewed cookie policy.
CORS is disabled by default and supports only exact configured origins. Browser
origins are checked on session requests, including login and uploads.

Scripts may instead send `X-Session-Token: <session-specific secret>`. Both cookie
and header access are checked against the requested session on every call. The
camera token grants no UI result/control access. The new auth routes use the
existing error envelope. Unknown session credentials are denied; an authorized
but not yet started session returns `state=idle`, `status=unavailable` and empty
objects. No public listing exposes other sessions.

## Controls and ordering

```sh
curl -b /tmp/stride-cookie.jar http://127.0.0.1:8000/vision \
  -H 'Content-Type: application/json' \
  --data '{"session_id":"demo-1","action_id":"action-001","action":"start"}'
```

Initial response without a result:

```json
{"session_id":"demo-1","action_id":"action-001","action":"start","state":"active","state_seq":1,"generation":1,"source_revision":0,"status":"unavailable","duplicate":false,"applied_state_seq":1}
```

| Current state | Accepted actions | Result |
| --- | --- | --- |
| idle | start, stop | active, stopped |
| active | pause, stop | paused, stopped |
| paused | resume, stop | active, stopped |
| stopped | none | Terminal: use a new session ID and credential to start again |

Every accepted transition invalidates pending frames, old publications and
speech. A physical running inference retains its claim until completion but
cannot publish into a later generation. Resume processes only newly received
frames; uploads that cross a control transition during JPEG validation are also
ineligible. Pause/stop do not replay old pending images.

Repeat an identical accepted `action_id` to retry safely: no transition occurs;
response `duplicate=true` contains the **current** authoritative state and the
original `applied_state_seq`. Reusing an ID for different contents returns 409.
Rejected transitions are remembered and replay the same error. Stop is terminal,
so delayed old starts/resumes cannot restart it. Optional `expected_generation`
provides an optimistic concurrency check (409 on mismatch).

`state_seq` increases for controls, source changes, publications and visible
status changes. Generation changes invalidate tracking/output identity; polling
alone never invents a new event/revision. Action history is bounded (128 records
plus one reserved stop record), never evicted to permit an old replay. At capacity
new actions receive 429, while the first terminal stop is still accepted.

## Frame and polling contracts

The Phase 1 `file` and metadata contract is unchanged: required `session_id`,
`device_id`, `boot_id`, `frame_id`, nonnegative `sequence`, `captured_ms`, and
`source=real|simulated|fixture`; optional `origin` and `source_revision` remain.
Device uploads use `X-Device-Token`. Phone uploads may use the session cookie or
`X-Session-Token` on the same endpoint, without learning the camera token; their
multipart session ID must match the authorized session or receive 403.

```sh
curl -b /tmp/stride-cookie.jar http://127.0.0.1:8000/frame \
  -F 'file=@/path/to/frame.jpg;type=image/jpeg' \
  -F session_id=demo-1 -F device_id=phone-1 -F boot_id=boot-1 \
  -F frame_id=frame-1 -F sequence=1 -F captured_ms=42 \
  -F source=real -F origin=phone-camera -F source_revision=0
curl -b /tmp/stride-cookie.jar 'http://127.0.0.1:8000/vision/latest?session_id=demo-1'
```

202 still means validated ingestion, not successful inference. Idle legacy uploads
retain Phase 1 store behavior; Start clears them. Paused/stopped controlled uploads
receive 202 but are discarded. Only active sessions dispatch. A source/boot/device/
origin switch in a controlled session must **increase source_revision**, otherwise
409; old revisions cannot switch the source back. Reset UI tracking on generation
or source revision changes. Production never treats fixture/simulated frames as
live; they are available for explicitly local development/tests.

`VisionLatest` in `models.py` and `/openapi.json` define the complete response.
Example response excerpt before any result:

```json
{"session_id":"demo-1","state_seq":1,"generation":1,"state":"active","status":"unavailable","detector_configured":false,"frame_id":null,"device_id":null,"captured_ms":null,"received_ms":null,"completed_ms":null,"age_ms":null,"source_revision":0,"source":null,"origin":null,"result_hz":0.0,"objects":[],"speech_event":null}
```

A fresh batch returns matching frame/device/boot/sequence metadata and objects
with `label`, finite `score`, normalized `[xmin,ymin,xmax,ymax]`, optional supplied
`track_id`, and image-relative `position=left|center|right`. Position uses the
horizontal box midpoint thirds, never distance or a safe walking direction.

Poll at up to 5 Hz while active. Responses/errors use `Cache-Control: no-store`.
`status=live` requires a validated fresh result, even if its objects are empty.
Paused sessions return `paused`; stopped/unstarted/no-detector/no-result sessions
return `unavailable`. Expired observations return `stale`, their age and identity
for diagnostics, **empty objects and null speech**. Errors suppress current output.
Ignore older state_seq values and clear overlays/audio when status is not live.
Before speech playback, add local monotonic time since response receipt to
`age_ms` and suppress output older than 1,000 ms; a cached response cannot stay
current merely because the browser has not polled again.

Optional supplied speech events contain `event_id`, `text`, `generation` and
`source_revision`. A poll of the same result preserves the same ID; announce once
per `(session_id,generation,source_revision,event_id)`, never once per poll. Seen
IDs cannot be reissued by later results in that generation. History is capped at
256; additional events are suppressed until a new generation. No event provider
means null. Frontend owns playback, cooldowns, interruption and page-hide controls.

## Detector integration

Implement the unchanged protocol:

```python
from stride_backend.models import DetectionBatch
from stride_backend.store import Frame

class MyDetector:
    async def detect(self, frame: Frame) -> DetectionBatch:
        # Use frame.jpeg; preserve frame.metadata exactly in the returned batch.
        ...
```

Register once with `create_app(settings, detector=instance)`, or provide a
zero-argument `build_detector()` factory and set
`STRIDE_DETECTOR_FACTORY=teammate_vision.adapter:build_detector`. No entrypoint
rewrite is necessary. Load/warm the model in the factory, not per frame. A factory
failure reports `detector_load_error` rather than substituting a provider.

Input Frame has immutable JPEG bytes, unchanged ReceivedFrameMetadata, internal
monotonic receipt time and a generation. Return `DetectionBatch(frame=frame.metadata,
completed_ms=<server epoch ms>, objects=<tuple of Detection>)`. Each Detection has
`label`, numeric score in [0,1], finite ordered normalized xyxy box and optional
track_id. Optional `speech_event=SpeechEvent(event_id=...,text=...)` is preserved
and deduplicated; omit it when the tracking/speech integration is not ready.

The worker revalidates all fields, including model instances built without
validation, exact receipt/session/frame/device/boot/source metadata, generation
and age. The backend stamps authoritative completion time when it receives the
model output. Frame metadata in the adapter input is never rewritten. Tracking
IDs/speech content come from the integration; backend fabricates neither.

A fixed number of workers (default one) await an arrival event, claim one newest
frame from the existing LatestFrameStore, and call the detector **off the HTTP
loop in a bounded thread pool**. Each async detect coroutine runs on its worker
thread's event loop; do not share HTTP-loop-bound async clients/locks with it.
Synchronous CPU work inside that coroutine is isolated from HTTP. Higher worker
counts share the same detector instance concurrently and require a thread-safe
adapter. Native runtime threads/processes remain the detector owner's choice.

Claims always release through finish(frame) in finally. Superseded pending frames
are dropped; a fresh in-flight result may publish while a newer frame waits.
Timeout/error/cancelled/old-generation/source-mismatched results cannot publish.
Errors expose categories, never exception messages/images/tokens. Common categories:
`detector_error`, `invalid_result`, `identity_mismatch`, `inference_timeout`,
`stale_result`, `detector_load_error`. A later valid result recovers automatically.

Run the opt-in real adapter test later, after installing its separate dependencies:

```sh
STRIDE_INTEGRATION_DETECTOR_FACTORY=teammate_vision.adapter:build_detector \
STRIDE_INTEGRATION_JPEG=/absolute/path/to/consented-photo.jpg \
python -m pytest -q tests/test_detector_integration.py
```

This uses the actual adapter and explicitly labels its static test photo fixture.
It is skipped without those inputs. It is not a real-camera throughput test.

## Timing, monitoring and limits

`captured_ms` is the unchanged camera timestamp. `received_ms` is server body
receipt; `completed_ms` is server inference publication; `delivered_ms` is the
poll response time. All local elapsed times use monotonic server clocks.
`receipt_to_result_ms` is explicitly not capture-to-result latency. Default age
is monotonic time since receipt; a recently completed slow result cannot reset it.
Live frames/results expire after at most 1,000 ms, including speech.

A trusted future clock-alignment integration can call
`store.register_clock_alignment(session_id, VerifiedClockAlignment(device_id,
boot_id, offset_ms, uncertainty_ms, valid_until_monotonic_ms))`. It must first
verify camera offset/RTT. Alignment expires within 60 seconds and only applies to
that device/boot. Age then conservatively includes capture delay and uncertainty;
responses mark `freshness_basis=aligned_capture`. No public upload can declare
itself aligned. Phase 1 receipt fields retain their original server-receipt
semantics. No aligned camera timestamps have been verified in this milestone.

Status distinguishes rolling camera `upload_hz`, completed `inference_hz`, and
fresh published `result_hz` (ten bounded 100 ms buckets). Counts include uploads,
completed calls, publications, dropped frames and superseded pending frames.
A successful upload alone never changes vision to live. Rates are observations,
not promised throughput. `/status` is session-authorized and includes state,
detector availability, result age, queue/claim counts and last error category.

Original bounds remain: 512 KiB JPEG, 4 million pixels, 8 sessions, 16 device/boot
histories per session, and full-body size cap including streamed requests.
Authentication precedes body reads and no images are persisted or logged.
Controlled sessions retain bounded history/tombstones for the application lifetime;
at the session limit, provision a new deployment/session allocation rather than
silently forgetting stopped sessions. Restart loses all in-memory history.

Python cannot kill arbitrary running native/thread code. On timeout its worker
retains the claim until return, preventing overlapping calls/queue growth.
Shutdown invalidates results, waits a configurable short grace then cancels the
async dispatcher and closes the executor to new work. An already running thread
can outlive that grace and delay process exit; adapters must enforce their own
bounded runtime. A stuck sole worker produces honest unavailable/stale output.

## Verification and remaining deployment gates

Verification: **140 passed, 1 skipped**, with one upstream Starlette/httpx
deprecation warning. `pip check` reports no broken requirements. The skipped
test requires the real detector adapter and a supplied image.

The full test suite covers Phase 1 plus lifecycle/idempotency, automatic dispatch,
slow/error/timeout/cancelled inference, generation/source races, stale results,
validation, event IDs, bounds, session cookies/authorization/CORS, worker startup
and shutdown. Test doubles exist only under tests; no YOLO throughput is claimed.

Real YOLO integration, sustained 5 fresh results/s, capture-to-result p95 <=500 ms,
hosted phone operation and physical W11/AirPods tests remain unverified. Choose a
host, provision session/camera secrets and exact UI origins, register the real
adapter, and run those gates. Single-process in-memory state is not shared across
workers or replicas. In this agent environment socket binding was denied during
Phase 1; run the documented command in a normal terminal for a network smoke test.

The root README is an older snapshot design. Updated requirements were read from
remote copies of [agent brief](https://github.com/adhyannsingal/stride/blob/main/Stride_Agent_Start_Here.md)
and [live vision requirements](https://github.com/adhyannsingal/stride/blob/main/Stride_Live_Vision_Requirements.md),
which override it. Only backend-owned files are changed.
