---
inclusion: always
---
# Technology and contracts

- Backend: Python 3.11+, FastAPI, typed Pydantic schemas, Uvicorn, SQLite. The combined serving application is `backend_phase3/stride_backend`, including Phase 4 devices.
- Vision: `app/vision/phase2.py` supplies `app.vision.phase2:build_detector`; YOLOv8n ONNX inference uses the intended model and matching checksum manifest. No fixture substitution in real mode.
- Frontend: phone web app in `frontend/`. Retain the exact pinned dependency versions and lockfile. No unnecessary infrastructure.
- Development: same-origin development proxy to FastAPI, normally UI 8443 and backend 8000. Production needs explicitly configured HTTPS, credentials, origins and persistent storage.

Use actual code/OpenAPI when older prose contracts differ. Implemented endpoints include GET /health, /time, /routes, /memory, /vision/latest, /device/status; POST /auth/session, /frame, /vision, /route, /device/pair, /telemetry; device command polling and acknowledgments.

`/frame` is multipart: file plus session_id/device_id/boot_id/frame_id/sequence/captured_ms/source/origin/source_revision. Sources are real/simulated/fixture; unavailable and stale describe status. `/route` uses action_id, navigation_id and expected_revision. `/vision` uses action_id and expected_generation. Retrying an uncertain mutation preserves its original ID and payload.

UI sessions use HttpOnly cookies or the explicit session-token contract; camera and controller credentials are separate. Never embed secrets in frontend code, logs, examples or Git. Retain root secret/model/database exclusions. Live controller state requires one server process/replica unless architecture is deliberately changed.

Verification from frontend: install from the lockfile, then run the frontend's test and production build scripts. Backend: use its configured Python environment and run `python -m pytest -q` from backend_phase3. Acceptance: `frontend/tests/run_acceptance.py` with real paths in STRIDE_BACKEND_CHECKOUT and PLAYWRIGHT_MODULE. Report skips and environment failures accurately.
