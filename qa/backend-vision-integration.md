# Backend + vision merged verification

Software branch ca9d6c8 merged with main 3cce971 on integration/backend-vision.
Merge SHA: 2854bd1; subsequent integration commit contains adapter, setup and this
report. Use git log for final pushed main SHA. No existing vision/firmware history
was reset and backend core modules were not replaced.

- Phase 1: 58 tests PASS, pinned Phase 2 dependency environment.
- Phase 2: 141 tests PASS, including its opt-in real YOLO adapter test using the
  explicitly labeled official bus fixture. No skipped provider test in that run.
- Combined vision/integration suite: 26 tests PASS; adapter tests cover immutable
  identity, track continuity/reset, bounded sessions, no unarbitrated speech,
  actual authenticated multipart upload/result/pause and bad-checksum fail-closed.
- uv pip check: PASS, 30 compatible installed packages. Isolated Python 3.11.16
  environment /tmp/stride-phase2-venv; existing model development env preserved.
- Actual loopback Uvicorn/HTTP camera test: PASS, 60.31 s,
  397 unique results, 6.58 returned
  results/s, 8.27 uploads/s, 0 HTTP errors.
- Actual capture-to-completion: p50 66 ms,
  p95 193.4 ms,
  max 594 ms.
- Poll-response capture age: p95 280.6 ms. These are
  separate completion/delivery timings, not audible speech latency.
- Clock basis: aligned_capture from trusted internal registration; camera/server
  ran on the same OS clock. No public upload could declare itself aligned.
- Model outputs included person/cup/bottle/laptop. Ground-truth accuracy was not
  assessed; candidates are not a coverage/safe-path claim. No raw frames retained.

Exact runtime report: phase2-webcam-http.json. Actual HTTP used multipart, session
header auth, source=real and the real ONNX model. No test detector substituted.
Random session/device secrets existed in process memory only and were not saved.
Server/session stopped after the measurement; no process/host deployment claimed.

Model-serving environment uses FastAPI 0.135.2/Pillow 12.3.0 from Phase 2 and the
same NumPy/ONNX Runtime versions as vision; Torch/export stack is absent. This
verifies compatibility under backend pins instead of silently changing them.

Known gaps are explicit in handoff/backend-vision-integration.md: API differences
from the planned contract, remote clock verification, explicit camera ownership,
central priority/audio, UI, routes/device APIs, deployment and physical hardware.
Default Phase 2 server-receipt age is not claimed to satisfy verified remote
capture freshness. W11 uploader raw-JPEG/camera-state protocol is not yet supported
by this milestone backend. Hosted phone/AirPods and laptop-free tests NOT RUN.
