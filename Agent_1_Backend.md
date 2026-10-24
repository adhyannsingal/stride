# Agent 1 — Stride backend

## Your assignment

Implement the backend end to end. Agent 2 owns the frontend. Agent 3 (Adhyann) owns hardware, firmware and the live vision model. These three briefs supersede previous agent numbering and ownership. Read `contracts/API.md`, `Stride_Live_Vision_Requirements.md` and the integration section of `Agent_3_Hardware_Vision.md`. Start implementation now; return working code and evidence, not another planning document.

Stride is navigation assistance glasses: checked-route guidance and Route Memory, immediate local obstacle alerts, continuous objects-ahead awareness, AirPods speech and directional vibration. Object finding is an additional feature. The final runtime is hosted FastAPI plus YOLO, reached by the glasses and phone. The Mac is for development. No native iOS app, LiDAR dependency, world-anchored audio or autonomous safe-path planning.

## Exclusive ownership

| You own | Other owner — do not implement or rewrite |
| --- | --- |
| `app/main.py`, `app/settings.py`, `app/schemas.py`, `app/db.py`, `app/dependencies.py` | Agent 2: all `web/`, browser capture, speech and UI |
| `app/api/`, `app/services/`, **all `app/devices/` server code** | Agent 3: all `app/vision/`, model export/runtime/tracking |
| `contracts/`, `requirements.txt`, `.env.example`, `.gitignore`, deployment configuration | Agent 3: all `firmware/`, device simulators and live measurement scripts |
| `tests/backend/`, `scripts/seed_demo.py`, `scripts/check_deploy.py`, `qa/backend.md` | Agent 3: physical assembly, wiring checks and hardware reports |
| Root README, shared startup/test instructions, app assembly and final integration merges | Agent 2: submission script; Agent 3: final integration evidence |

Shared files have **one writer: you**. Other agents submit exact dependency/settings/schema requests in their handoff files; you apply compatible changes. Do not put a placeholder detector into Agent 3's directory. If existing code uses different paths, publish the ownership map before moving anything. Preserve working teammate code and uncommitted changes.

## Implement in this order

1. Fetch current `main` and inspect `software` and actual working code. At review, `main` was `905b2218a142be9b20696ba823db63444e9b5f91`, and `software` was `5cc61fde5f1b65764d5dc8f47aab28be52122aa1`; both were docs-only. `Phase_1` was a planning file, not completed code. Recheck rather than assuming the repo is still empty. Use one FastAPI app, Python 3.11, Pydantic v2, SQLAlchemy/SQLite and a single serving worker while state is process-local.
2. Within the first 20 minutes of actual remaining work, publish canonical schemas, request examples, `/health`, auth/session creation and a usable backend URL. Check the actual deadline; do not restart the six-hour clock. Keep endpoints explicitly unavailable until implemented. Agent 2 uses fixtures in its own adapter; production responses never fabricate success.
3. Implement auth, sessions, selected camera/source revision, bounded JPEG ingest and validated telemetry. Accept real browser/W11 JPEGs through **one** `/frame`. Feed Agent 3's service after validation; no second frame endpoint. Reject malformed/oversized images, wrong bindings, old boot/sequence and obsolete source revisions. Require the server-issued `X-Source-Revision` header from both browser and W11 uploads.
4. Implement routes and Route Memory: saved checked steps, manual checkpoint confirmation, repeat/pause/resume/stop, action-ID idempotency, progress persistence and last-seen records. Repeating never advances; duplicate confirmation advances once. Recall includes capture time, age, source and last-confirmed checkpoint; it is not a current location guarantee. Supply a demo route marked illustrative until physically checked.
5. Implement the **server side** of feedback: telemetry freshness, device/session binding, alert priority, one pending command/device, TTL, generation/boot checks, command polling and ACK state. Agent 3 implements the firmware client and simulator against this service. Do not write a competing firmware simulator or ask Agent 3 to implement the server queue.
6. Assemble Agent 3's vision router/service using the exact seam below. Extend `/status`, persist eligible observations, and arbitrate output centrally. Optional Gemini describe/find is timeboxed after the integrated live path passes. Find can filter supported YOLO labels first; `mug` may map visibly to model class `cup`. Never claim recognition outside the selected class set.
7. Deploy the combined app and serve Agent 2's `web/` from the **same HTTPS origin**. Pin serving dependencies including Agent 3's requested runtime; conversion tooling stays out of the deployed environment. Configure model location/checksum, memory/CPU and one worker. Report the actual URL and persistence limits. Deployment access missing is a specific blocker, not a completed deploy.

## Public interface you own

Use `contracts/API.md` for full payloads. Keep snake_case, UUID action/event IDs, integer epoch milliseconds and structured errors. Required routes:

| Interface | Responsibility |
| --- | --- |
| `GET /health`, `POST /auth`, `GET /time` | Readiness/commit, rate-limited access-code login with secure HttpOnly cookie, clock alignment |
| `POST /sessions`, `POST /sessions/{id}/devices`, `POST /sessions/{id}/camera` | Mode/bindings, server-derived provenance and source invalidation |
| `POST /routes`, `GET /routes`, `POST /route` | Route definitions and authoritative state transitions |
| `POST /frame` | Authenticated raw JPEG; validate, retain bounded latest frame, offer to vision service |
| `GET /status`, `GET /memory`, `GET /memory/export`, `POST /memory/import` | One authoritative state/priority view; durable data and validated route import |
| `POST /telemetry`, `GET /devices/{id}/commands`, `POST /devices/{id}/ack` | Physical device protocol; device-token auth, binding/boot checks |
| `POST /simulation/telemetry`, `POST /simulation/ack` | Explicit simulation mode only; simulated sessions cannot operate real devices |
| `GET /devices/{id}/camera-state?session_id=...` | **New agreed seam:** camera-token auth; selected/active state, `source_revision`, `state_seq`, server time. W11 must not depend on UI cookies. |
| `POST /vision`, `GET /vision/latest` | Agent 3 supplies router; you mount it and supply shared auth/state dependencies |
| `POST /perception` | Optional requested Gemini path; never the automatic detection loop |

Publish the exact camera-state response in the shared schema before firmware work: `session_id`, `device_id`, `selected`, `active`, `source_revision`, `state_seq`, `server_time_ms`. Inactive/unauthorized/unreachable state suppresses W11 uploads; no frame backlog on recovery. Browser source changes also return the revision to the frontend.

## Python seam with Agent 3

Agent 3 supplies `app.vision.router.router` and one `VisionService(settings)` with `start()`, `close()`, `control(session_id, action, source_revision)`, `offer_frame(frame)`, `snapshot(session_id, now_ms)`, and `invalidate(session_id, source_revision)`. Freeze typed signatures in `contracts/API.md` together; backend owns canonical API models, Agent 3 owns internal detector types. `offer_frame` is quick/nonblocking and retains one newest pending frame per session.

You instantiate **one** service in FastAPI lifespan, expose `app.state.vision`, mount its router once and call its lifecycle methods. `/frame` passes validated JPEG bytes plus canonical frame metadata. Route pause/stop and camera/session replacement control/invalidate the same instance. Do not load a second model or maintain another inference queue. Agent 3 reports observations through an injected async callback; your callback persists eligible sightings and publishes centrally arbitrated speech events. It must not block the inference loop on database/network work.

`/vision/latest` carries Agent 3's detections plus the centrally authorized speech event; `/status` uses the same event IDs/state. `/status` and latest responses must not independently mint announcements. Local urgent obstacle > fault > route > observation. Suppress stale observations and cancel pending remote turns on pause/stop/rebind/urgent alert; physical local sensing always remains active.

## Required correctness

- Maximum JPEG 1 MB; longest side 1920 and total pixels at most 1920×1080; validate actual decoding. Default 640×480. Raw frames are bounded memory only; do not retain private camera images in Git or logs.
- `source=real|simulated|fixture`, `origin` identifies adapter, and health is separate. Never call a fixture real. Bind bearer tokens to role/device/session; body IDs do not authorize requests. Secrets stay server-side/ignored device config.
- Live results older than **1000 ms** are unspeakable; unsynced/unverifiable capture age cannot be presented as fresh. Gemini's separate snapshot window does not relax live expiry. No depth or safe-turn instruction from boxes.
- Command TTL is at most 1500 ms from creation. Return **remaining** TTL, deduplicate IDs/actions/ACKs, reject retired boots and never replay on reconnection. ACK completion is firmware-reported; show physical output as unverified until observed.
- Use explicit disconnected/invalid/stale state and deduplicated faults; don't replay queued route instructions after recovery. Backend cancellation occurs when received; it cannot guarantee instant remote cancellation across a network outage.
- SQLite durability depends on actual hosting disk. State the limit and provide export; do not add Redis, TimescaleDB, account systems or paid resources for this sprint.

## Proof and handoff

Run focused backend tests for auth/binding, duplicate route actions, frame/source ordering, TTL/boot/ACK behavior, stale/invalid telemetry, simulation isolation, memory filtering and vision adapter integration. Prove `/frame` offers to the real service once and pause/source-switch prevents old publication. Record exact commands/results in `qa/backend.md`.

Deliver `handoff/backend.md`: commit, launch/test commands, environment names, deployed URL, API examples/OpenAPI, agreed model settings, current blockers and endpoints actually tested. Keep README runnable. Use configured Git identity without Codex attribution; no force-push, secrets or purchases. Merge small reviewed slices every 45 minutes, not only at the end.
