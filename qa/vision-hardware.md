# Agent 3 — vision/hardware acceptance

Baseline main `85d445f`, branch `stride/hardware-vision`. Source changes and
this evidence are in the Agent 3 commit (`git log -1 --oneline`). Report prepared
2026-10-24 UTC. Actual build/submission deadline and hosted URL were not supplied.
MacBook Air M4 development runtime, Python 3.11.16, ONNX Runtime CPU 1.31.0,
Ultralytics 8.4.187. No actual ESP32 USB board was identified by CLI inventory.

| Gate | Result | Actual source/evidence |
| --- | --- | --- |
| Python vision + contract harness | PASS | 19 fixture tests: `.venv/bin/python -m pytest tests/vision tests/integration -q`. One upstream TestClient deprecation warning. Includes real service mounted into a test-only canonical backend, auth rejection, action retry, offer/callback, normalized boxes and pause. |
| Load once / bounded overload | PASS | Fake detector/clock: two concurrent starts load once; 50 pending offers collapse to newest; callback backlog is one newest result and slow callback does not block inference. |
| Stale/source/pause/stop | PASS (policy) | Future/unsynced/retired offers rejected; late completion discarded; read-time age strips objects; source retirement cancels callbacks and `is_current` becomes false. |
| Stable candidates and priority boundary | PASS (policy) | Two observations, stable IDs/cooldown tested. Raw latest never emits speech. Backend final priority/playback still needs actual integration. |
| Original versus ONNX export | PASS | Official bus/zidane fixtures; `export-comparison.json`. Max raw abs error 0.00110, same labels/boxes within .001 normalized. Not a scene accuracy or live test. |
| Updated real webcam throughput | PASS (local performance) | `agent3-webcam.json`: 60.022 s, 357 automatic results, 5.95 results/s; p50 38 ms, p95 90.2 ms, max 445 ms, zero pending drops/capture rejections. Actual webcam, no repeated clicks, raw images not saved. |
| Webcam startup handling | FAIL retained, corrected | `agent3-webcam-startup-failure.json`: slow initial capture expired. Harness now counts rejected old capture without restamping it; final run above passed. Earlier prior-turn runs also preserved locally. |
| Runtime resources | See agent3-local-resources.json | Five-second fixture-only local process measurement; peak RSS includes OpenCV/Python/capture harness. Not host capacity or hosted live proof. |
| Simulation client isolation | PASS (fixture transport) | Only /simulation/telemetry, /simulation/ack and /status; fails if response reports real feedback. Real backend scenario tests remain blocked. |
| Native controller | PASS | clang++ C++17 -Wall -Wextra -Werror; tests/vision/controller_test.cpp runs successfully: unknown, bands/hysteresis, patterns, ID dedup, TTL, link cancellation. |
| DevKit firmware compile | PASS | Arduino-ESP32 3.3.2 / ArduinoJson 7.4.2; `esp32:esp32:esp32`; 898163 bytes flash, 44200 bytes globals. `feedback-compile.txt`. Network-disabled example config. No flashing/output claim. |
| Camera uploader syntax compile | PASS (syntax only) | `esp32:esp32:esp32s3`, STRIDE_CAMERA_COMPILE_ONLY; 995483 bytes flash, 44752 bytes globals. `camera-syntax-compile.txt`. Board init excluded; binary cannot initialize hardware. |
| Unconfigured W11 gate | PASS (expected failure) | Normal compile fails at explicit board verification assertions: camera-board-gate.txt. Unknown map was not invented. |
| Canonical API + hosted phone | BLOCKED | Agent 1 executable app/mount/URL not available. Backend bridge requests are in handoff/vision-hardware.md. No deployed app is claimed. |
| Actual W11 glasses → host → iPhone/AirPods | BLOCKED | Exact PCB/vendor pins/memory facts, physical board and actual backend/phone test required. |
| Physical sensor/motor/offline alerts | NOT RUN | No rail/divider/regulator, calibration, waveform, mounting, heat or 15-minute powered evidence. Firmware compile/ACK cannot establish physical output. |

## Remaining release gates

- L01: performance portion passed locally; moved/new/removed supported objects
  under controlled observation NOT RUN. Webcam/API timing is measured from the
  host capture-read request; actual sensor exposure/driver buffering is not measured.
- L02/L03: deterministic overload/source/expiry policy passed; real host/network
  slowdown, disconnect/reconnect and latency tests remain NOT RUN.
- L04: candidate stabilization tested; backend urgent-priority + actual interruption
  on iPhone/AirPods and physical local alert remain NOT RUN.
- L05: W11 and no-carried-Mac deployment path BLOCKED, separately from webcam.
- L06: supported-class coverage/missed-hazard test NOT RUN. No universal hazard,
  depth, exact distance or safe-path claim is made.

`models/manifest.json` is the current exported artifact manifest. The 60-second
webcam process loaded the prior export before a re-export command ran; its JSON
records that actual loaded hash. Re-export parity passed on the current file.
Artifact metadata may change hashes even with the same checkpoint and outputs;
deploy the matching generated model/manifest pair. Heavy conversion tooling is
local only. CPU/RAM performance on a hosted allocation is NOT measured here.

## Next available integration action

Agent 1 mounts router/service and supplies canonical VisionAPI bridge; Agent 2
consumes normalized boxes and final backend speech events. Run live_smoke and
simulate_feedback on the actual deployed URL, then stop the Mac app server and
check the real iPhone. Human Adhyann identifies W11 and performs staged electrical
bring-up using firmware/README.md and the root wiring guide. No account purchase,
external message, remote push, physical flash or deployment was performed.

## Independent bench-mode follow-up

Sensor-only, buzzer-only, motor-only and normal-mode firmware all compile for
ESP32 core 3.3.2. See feedback-selftest-compile.txt. Native tests prove one 100 ms
pulse after 2 s, no repeat and no late replay. Sensor-only logs at 10 Hz while
keeping output drivers OFF; all bench modes disable networking. These checks
require no backend. Actual component measurements/USB flashing remain NOT RUN.

## Latest webcam/fault follow-up

See [webcam-tuning.md](webcam-tuning.md) for the newer visible-scene 60-second run,
profiling, reproduced source-worker buildup/fix, 22 passing Python tests and all
seven measured local camera/model fault cases. Initial dark-input measurements
are explicitly distinguished from scene recognition. Hosted/network/phone and
physical hardware release gates above remain unverified.
