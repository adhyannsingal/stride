# Combined backend and vision — merged integration

Software branch `ca9d6c8` (Phase 1 + Phase 2) is merged with main's vision and
firmware history. Phase 1 remains an archived milestone in backend_phase1;
**run Phase 2** from backend_phase2. Both milestones use the package name
stride_backend, so never put both backend directories on the same PYTHONPATH.

The model plugin is `app.vision.phase2:build_detector`. It uses the existing
Phase 2 factory/worker/store/router. No second FastAPI app, inference queue,
VisionService or vision router is mounted in this combined configuration.
`app/vision/service.py` and its tests remain available as standalone component
work; the combined runtime uses Phase 2's authoritative lifecycle and publication.

## Verified installation and launch

From repository root, Python 3.11:

```sh
uv venv --python 3.11 .venv-phase2
uv pip install --python .venv-phase2/bin/python -r backend_phase2/requirements-vision-dev.txt
PYTHONPATH=.:backend_phase2 STRIDE_LOCAL_DEV=true STRIDE_DETECTOR_FACTORY=app.vision.phase2:build_detector .venv-phase2/bin/python -m uvicorn stride_backend.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

The generated ONNX model must exist first. For export on a DEVELOPMENT machine,
use a separate environment (Torch/export tooling does not belong on the host):

```sh
uv venv --python 3.11 .venv-model
uv pip install --python .venv-model/bin/python -r app/vision/requirements-dev.txt
PYTHONPATH=. .venv-model/bin/python scripts/export_model.py
```

This downloads the pinned official checkpoint, verifies its checksum, and writes
models/yolov8n.onnx plus matching models/manifest.json. Model binaries are ignored
by Git. An existing generated model/manifest pair can instead be transferred to
the serving machine. Regeneration can change ONNX export metadata/hash; retain
the matching generated manifest. Upstream model/license references remain there.

For the serving host install **backend_phase2/requirements-vision.txt only**. The
-dev manifest adds pytest/httpx/OpenCV for diagnostics; no Torch is installed by
that manifest. Do not combine Phase 2's pinned serving requirements with the
older standalone app/vision/requirements-runtime.txt environment. Combined stack
was checked with FastAPI 0.135.2, Pillow 12.3.0, NumPy 2.4.6, ONNX Runtime 1.31.0.
`uv pip check` reports compatible installed dependencies.

Factory configuration:

- STRIDE_DETECTOR_FACTORY=app.vision.phase2:build_detector
- LIVE_DETECTOR_MODEL_PATH: optional explicit model path; defaults to repository
  models/yolov8n.onnx. Export this into the process environment if overriding it.
- LIVE_DETECTOR_MODEL_SHA256: optional process environment checksum; otherwise
  load the sibling manifest.json hash. A mismatch fails closed.
- STRIDE_MAX_SESSIONS: same bounded capacity used by backend and tracker cache.
- One Uvicorn worker/instance; default STRIDE_INFERENCE_WORKERS=1. The plugin
  serializes model calls even if more backend worker threads are configured.

Phase 2's Settings reads STRIDE_* values from .env; it does NOT export arbitrary
LIVE_* values into the process for the plugin. The default model path needs no
LIVE_* override. See backend_phase2/README.md for production session secrets,
device token, exact origins and HTTPS. Local-dev auth bypass is loopback-only
work, not hosting configuration. `/health` alone is not model readiness: confirm
`detector_configured` and actual results from an authorized vision session.

## Actual Phase 2 HTTP compatibility map

The existing Phase 2 API differs from the planned contracts/API.md. These are
explicit compatibility facts, not silently renamed endpoints. Core backend HTTP
behavior was preserved during integration; Agent 1 should coordinate any later
migration with Agent 2 and firmware.

| Planned interface | Implemented Phase 2 interface |
| --- | --- |
| POST /auth with access code | POST /auth/session with provisioned session_id + session_token; HttpOnly cookie, or script X-Session-Token header |
| POST /sessions | Provision session credentials through STRIDE_SESSION_TOKENS; first accepted /vision start creates runtime state |
| Raw JPEG /frame + X-* metadata, Bearer camera token | Multipart /frame: file JPEG + session/device/boot/frame/sequence/captured_ms/source/origin/source_revision form fields. UI cookie/X-Session-Token or device X-Device-Token. 202 receipt. |
| /time.server_time_ms | /time.server_ms |
| objects[].box, normalized XYXY | objects[].bbox, same normalized XYXY geometry |
| Server-selected camera/source via session camera route | Uploads with increasing source_revision currently switch identity; explicit producer-selection endpoint is not present |
| /status route/feedback/vision | /status currently contains backend + vision only |
| Device-authorized camera-state / telemetry / commands / ACK | Not implemented in these two milestones |

`POST /vision` uses session_id/action_id/action. Stop is terminal in Phase 2;
provision/use a new session to start again. Retry an action with its same ID;
never issue another raw start while already active. Viewer clients only poll the
same authorized session; they must not upload or implicitly change producer.

The plugin preserves the exact immutable receipt/session/device/boot/frame
metadata and generation. It converts our detector boxes to backend Detection.bbox,
resets tracks on generation/source identity changes and returns no fabricated
labels, depth or turns. It emits **no final speech_event**: Phase 2 has no
sensor/route priority arbiter yet. Agent 1/2 must integrate prioritized events
before claiming iPhone/AirPods announcement behavior.

Default freshness is **server receipt age**, explicitly labeled in responses.
Remote camera clock verification is not implemented by this merge; do not label
receipt-age measurements capture-to-result or enable current-scene walking
speech on unverified capture age. Phase 2 exposes a trusted internal
register_clock_alignment seam. The local HTTP benchmark uses it because its
camera and server share the same OS clock. This is not a public client assertion
or proof that hosted iPhone/W11 clocks are aligned.

## Tests and actual HTTP webcam proof

```sh
# Milestones independently (avoid their duplicate test module/package names):
(cd backend_phase1 && ../.venv-phase2/bin/python -m pytest -q)
(cd backend_phase2 && ../.venv-phase2/bin/python -m pytest -q)
# Combined integration and vision tests:
PYTHONPATH=.:backend_phase2 .venv-phase2/bin/python -m pytest tests/vision tests/integration -q
# Actual loopback HTTP with real webcam/model and in-memory ephemeral auth:
PYTHONPATH=.:backend_phase2 .venv-phase2/bin/python scripts/measure_phase2.py --seconds 60
```

Run Phase 2's opt-in original real-detector test by setting
STRIDE_INTEGRATION_DETECTOR_FACTORY=app.vision.phase2:build_detector and
STRIDE_INTEGRATION_JPEG to an absolute path of an explicitly labeled fixture.
Include the repository root on PYTHONPATH. The official bus fixture under ignored
qa/private was used here; no fixture is presented as a live camera frame.

The webcam harness starts the EXISTING create_app on loopback, supplies random
credentials only in memory, verifies actual multipart/auth/worker/poll behavior,
stops the session/server and saves aggregate measurements. It does not create a
replacement app or publish a hosted URL. qa/phase2-webcam-http.json records the
60-second result and the trusted-local-only clock alignment scope.

For an existing authorized backend, set STRIDE_SESSION_TOKEN privately (or
STRIDE_UI_COOKIE) and use a NEW idle provisioned session, with all other capture
producers stopped:

```sh
PYTHONPATH=. .venv-phase2/bin/python scripts/live_smoke.py --protocol phase2 --base-url https://HOST --session-id PROVISIONED_SESSION --device-id SELECTED_CAMERA --seconds 60 --output qa/phase2-hosted-smoke.json
```

Without the trusted same-process benchmark hook, this client does not register
remote clock alignment. Its result labels the backend freshness basis honestly.
The default --protocol canonical preserves the planned raw-JPEG diagnostic path;
choose Phase 2 explicitly. Source replacement aborts without stopping the new
producer. Secrets are never command-line arguments or report fields.

## Remaining release gates

- Agent 2 frontend integration for the actual auth/frame/bbox shape and viewer role.
- Hosted HTTPS deployment, model artifact delivery/capacity, and phone/AirPods.
- Trusted remote capture time verification, central priority/speech events.
- Explicit camera producer/device bindings and server-derived provenance.
- Routes/memory/device telemetry/command/ACK policies beyond these milestones.
- W11 raw-JPEG/camera-state firmware API compatibility and physical board facts.

No framework rewrite or backend core/controller replacement was made. See
qa/backend-vision-integration.md for measured checks and the integration commit.
