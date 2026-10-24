# Stride

AI-powered navigation assistance glasses for blind and low-vision users: checked-route guidance, immediate obstacle alerts, continuous objects-ahead awareness, AirPods speech and directional vibration. Object finding and last-seen recall support the navigation experience.

**Status:** backend Phase 4 is integrated into `backend_phase3/` (version 0.4.0) together with the real YOLO detector and firmware work. SQLite saved routes, confirmed checkpoint progress and last-seen memory are implemented and tested. The local live box preview is working. Device telemetry, conservative route holds and expiring haptic commands are implemented. Phone UI/API integration, central speech arbitration, audible AirPods testing, camera producer policy and physical hardware remain pending. See [Phase 4 integration](handoff/phase4-integration.md). See [current delivery evidence and remaining work](handoff/four-hour-delivery.md); the earlier [Phase 2 compatibility map](handoff/backend-vision-integration.md) remains useful for auth/frame fields.

## Run the combined backend locally

From the repository root (Python 3.11):

```sh
uv venv --python 3.11 .venv-phase3
uv pip install --python .venv-phase3/bin/python -r backend_phase3/requirements-vision-dev.txt
# Requires generated models/yolov8n.onnx + matching models/manifest.json.
# Model export/setup is documented in handoff/backend-vision-integration.md.
PYTHONPATH=.:backend_phase3 STRIDE_LOCAL_DEV=true STRIDE_RECORD_STABLE_SIGHTINGS=true STRIDE_DETECTOR_FACTORY=app.vision.phase2:build_detector .venv-phase3/bin/python -m uvicorn stride_backend.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

Open `http://127.0.0.1:8000/docs`. Local development mode is for loopback testing;
provision the backend's session/device secrets and HTTPS before hosting. Phase 3
uses multipart `/frame`, `/auth/session`, `/time.server_ms` and object `bbox`;
these differences from the planned shared contract are documented in the handoff.
There is one backend worker/controller; the YOLO plugin does not add a second one.

## Team assignments

| Owner | Responsibility | Give the agent this file |
| --- | --- | --- |
| Agent 1 | Backend, contracts, route/memory, server device policies, deployment | [Backend brief](Agent_1_Backend.md) |
| Agent 2 | Frontend, automatic browser capture, accessible controls and speech | [Frontend brief](Agent_2_Frontend.md) |
| Agent 3 — Adhyann | Vision model/service, W11/DevKit firmware, hardware and integration | [Hardware/vision brief](Agent_3_Hardware_Vision.md) |

Each brief defines exclusive paths, interfaces, implementation order, tests and handoff. Agent 1 owns shared files. Agent 3's **Integration plan for all three agents** explains branch/merge order and time gates. These assignments supersede older briefs.

## What we are building

- Guided routes with explicit checkpoint confirmation, repeat/pause/stop and Route Memory.
- Continuous live recognition after one Start, using fresh frames and stabilized announcements.
- Independent HC-SR04 proximity warnings via a separate ESP32, buzzer and protected 3 V motor.
- Spoken route/object/fault events through the iPhone and AirPods; distinguish real versus simulated output.
- Find supported objects and recall last-seen timestamp/checkpoint/source. Optional Gemini adds requested descriptions after the core passes.

```text
W11 glasses camera → HTTPS JPEG → hosted FastAPI + YOLO → iPhone web app → AirPods
HC-SR04 → DevKit → local buzzer / protected 3 V motor (works without cloud)
Checked route → backend → expiring direction command → DevKit
```

MacBook/webcam is for development; no carried laptop in the final runtime. Browser/phone camera and sensor simulation unblock development tonight and remain visibly labeled fallbacks. OpenCV supports image handling; YOLO does detection. Gemini is outside the continuous loop.

## Build and integration

Start with [the team build spec](buildspec_stride.md), [shared API](contracts/API.md), [live requirements](Stride_Live_Vision_Requirements.md) and [full hardware wiring guide](Stride_Hardware_Wiring_Guide.md). A current [handoff ZIP](Stride_Team_Handoff.zip) contains the same agent briefs/contracts plus QA and submission templates. Agents should use repository files directly; extracting the ZIP over a working checkout is unnecessary.

The shared contract fixes one frame endpoint, a mounted vision service, a backend-owned feedback arbiter and frontend-owned speech playback. Merge small working slices every 45 minutes. Prove phone → hosted detector → phone first, then sensor simulation/commands, then W11 and physical hardware. Reserve final build time for hardware checks and a separate hour for video/submission. Use actual remaining time.

Target 5 fresh detections/s and capture-to-result p95 ≤500 ms over 60 s; measure, do not assume. Frames older than 1000 ms are not current-scene speech. Late frames/events, duplicate actions and expired commands must not replay. Missing detection never means clear path. A fixed-label detector cannot guarantee every hazard, metric depth or a safe turn.

Exact W11 pinout is still a vendor/PCB verification gate. HC-SR04 ECHO needs a divider; the 3 V motor needs a regulated supply/driver/diode. Standard iPhone 14 has no LiDAR. Normal AirPods speech is included; world-anchored audio is not a required or proven feature.

## Before claiming completion

Each agent supplies actual launch/test commands, commit, passing checks and blockers in its own `handoff/` and `qa/` file. Backend owner updates this README with verified runnable setup once code exists. Keep secrets/images/databases out of Git and use configured Git attribution.

Demonstrate on a checked controlled route with a sighted spotter. Stride targets navigation assistance; this prototype is not validated for independent blind walking or road crossings.

## Webcam demo before hardware arrives

Open the app on Mac as the explicit camera source; open the same session on iPhone in viewer/audio mode. Mac webcam → hosted YOLO → iPhone/AirPods. The phone must not auto-start its camera or change the selected producer. The frontend/backend agents must implement and verify this mode; these docs alone do not add it to an app. Agent 3 prepares both firmware projects while waiting for the parts, expected in 2–3 hours, then starts staged hardware bring-up.

## See real webcam boxes now

After installing the vision development dependencies and model above:

```sh
PYTHONPATH=. .venv-phase3/bin/python scripts/preview_live.py
```

Focus the window: **P** pauses/resumes, **Q/Esc** quits and releases the camera;
**+/-** changes only diagnostic confidence. Labels include score and image
left/center/right. This is a local detector preview; it does not upload frames,
record memory or speak. Close/pause it before another process opens the webcam.
Image position does not establish depth, walkable space or a safe direction.

Phase 3 exposes authenticated `GET /routes?session_id=…`, `POST /route` and
`GET /memory?session_id=…`. Import a custom named route using
`scripts/import_saved_route.py` with `PYTHONPATH=.:backend_phase3`; see
[the current handoff](handoff/four-hour-delivery.md) for verification and API details.

## Speak webcam objects and bring up the motor

`PYTHONPATH=. .venv-phase3/bin/python scripts/preview_live.py --speak` enables optional Mac system speech in the local object-awareness preview. Select AirPods as Mac audio output. This is separate from the pending phone/backend speech integration and generates no avoidance directions. Follow [the step-by-step audio, sensor and 3 V motor bring-up](handoff/audio-haptics-bringup.md); the confirmed 3 V component is a vibration motor, and a buzzer is optional.

### Reliable Mac launcher

Double-click `Start_Stride_Demo.command` in Finder, or run `./Start_Stride_Demo.command` from this checkout. It resolves the checkout folder, checks the prepared Python/model, and keeps interactive errors visible. With `--speak`, a voice may need 2–3 seconds to start; narration continues only while fresh frames confirm that class/image position, is cancelled on lost/stale input or pause, and has a bounded maximum duration.
