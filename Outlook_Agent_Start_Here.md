# Outlook — agent kickoff and Phase 1 review

## Read this first

Implement Outlook's **continuous live vision, device/firmware integration and final end-to-end delivery** while two teammates build the frontend and backend. Do not duplicate their application or overwrite their work. This brief replaces the earlier three-agent file ownership where it conflicts with the team's updated allocation.

Product purpose: navigation assistance for blind and low vision users, with continuous objects-ahead awareness, spoken instructions through AirPods and directional vibration. Object finding is secondary. One Start activates the vision loop; repeated Analyze clicks are not acceptable as the primary behavior.

**Repository:** `https://github.com/adhyannsingal/stride`.

**Reviewed branch:** `software`, commit `5cc61fde5f1b65764d5dc8f47aab28be52122aa1`. The root contains `Phase_1`, `README.md` and `buildspec_outlook.md` only. `Phase_1` is a plain-text planning prompt, not executable code. Recheck remote HEAD and all current working changes before starting; teammates may have added implementation since this review.

**Time:** the six-hour build clock is already running, followed by one hour for recording/submission. Ask the human for the actual remaining time/deadline if it is not visible; meanwhile begin independent work. Do not restart a six-hour clock or wait for another long planning cycle.

## Phase 1 verdict

**Keep the foundation, correct the scope immediately.** The document correctly calls for modular FastAPI, typed schemas, route state, hardware-free simulation, source/freshness handling, local-alert independence, expiring commands and tests. Those are useful and should not be thrown away.

It is insufficient as the current project execution brief:

| Issue | Evidence in reviewed `Phase_1` | Required correction |
| --- | --- | --- |
| No mandatory live recognition | Lines 35–43 and 49 reserve perception for future Gemini; lines 110–119 can pass without real images or a running detector | Add automatic frame ingestion → continuous hosted YOLO → fresh results → phone feedback. Keep Gemini optional. |
| Laptop retained as runtime | Line 9 assigns backend/database/AI to the Mac | Mac is development only; deploy the runtime to a phone-reachable HTTPS host. Verify with Mac dev server stopped. |
| Obsolete time and team allocation | Line 5 says 36–48 hours and one software teammate; line 17 says `feature/software` | Use actual remaining six-hour sprint, two frontend/backend teammates and this vision/device integration owner. Actual reviewed branch is `software`; recheck before branching. |
| Planning/serial phase gate can consume the deadline | Lines 25–27 and 123–131 require additional specs/approval before implementation and postpone later work | Keep a short shared-contract check; execute independently owned vertical slices in parallel. A backend skeleton can be one milestone, not the release gate for everyone else. Honor any separate human-required approval that still applies. |
| Missing live acceptance and deployment checks | Acceptance covers startup, mocks and route tests only | Add sustained live rate/age, no-backlog/fault behavior, actual iPhone audio and hosted no-carried-laptop checks. |
| Source and health mixed together | Line 84 calls `unavailable` a source; line 117 mixes stale/unavailable with provenance | Separate `source=real|simulated|fixture`, adapter origin and health `live|stale|unavailable|paused`. Never label missing hardware real. |

**Verification limit:** no application/tests/dependency manifest were present in the reviewed tree, so this review validates the plan's alignment only. It does not verify that FastAPI starts, pytest passes, AI works or hardware is integrated. Do not report any of those as tested.

## Team ownership

| Owner | Responsibility | Boundary |
| --- | --- | --- |
| Backend teammate | FastAPI app assembly, auth/sessions, canonical contracts, routes/memory/database, shared status, backend hosting settings/secrets | Owns shared `main.py`, shared schemas/settings/dependencies. You supply a detector/router and integration patches, not a competing backend. |
| Frontend teammate | iPhone/web interface, camera capture, automatic uploads, overlays, route controls, browser speech/AirPods, accessible live health | You supply exact events, payloads and a test client. Do not rebuild their UI. |
| **You, this agent** | Live detector/model runtime, newest-frame pipeline, firmware/device adapters, integration test harness, performance/fault evidence and release coordination | Own new vision/firmware/integration modules after checking current files. Humans wire hardware at the end; you prepare and verify software/configuration. |

Coordinate a deployment smoke test with the backend teammate early. Whoever has hosting access performs the deploy; your acceptance responsibility is verifying the actual running URL and live performance. Never claim a deployed service because a configuration file exists.

## Locked architecture

```text
W11 on glasses ── automatic fresh JPEGs ── Hosted FastAPI + lightweight YOLO
                                                    │
                                   fresh detections / stable event IDs
                                                    ▼
                                          iPhone → AirPods speech

Checked route → route instruction → expiring motor command → DevKit
HC-SR04 → independent DevKit loop → local buzzer / protected 3 V motor
Gemini → optional requested description or unusual-object query
```

No laptop is carried. On-phone Core ML is a possible later optimization; do not start a new native iOS app during this sprint. The standard iPhone 14 has no LiDAR. AirPods provide ordinary spoken audio; room-anchored/head-tracked sound is not a required or proven feature.

## Start implementing in this order

### 1. Inspect and agree on the seam — first 10–15 minutes

- Fetch current branches/HEAD, read applicable repository instructions and inspect existing uncommitted code. Reuse working code; do not reset it.
- Confirm frontend/backend ownership and shared endpoint names. Briefly flag the Phase 1 corrections above to the human; do not autonomously send messages to other people/services without authorization.
- Obtain the current FastAPI interface or supply an importable detector service and router the backend can mount. Do not block model testing on the entire backend being complete.
- Use current contracts if they already implement the semantics below. If URLs or field names differ, provide one explicit compatibility map and coordinate it; no silent frontend/backend protocol fork.

### 2. Prove actual continuous detection — next 30 minutes

- Select a small pretrained YOLO detector; record model/version, exact classes, input shape, preprocessing, output decoding and NMS behavior.
- Prove it on real webcam images locally. Use prerecorded/synthetic images only for tests, visibly labeled.
- For hosted inference, prefer an exported ONNX model plus ONNX Runtime if it meets actual host CPU/memory and latency gates. Use original/exported output comparisons to catch incorrect decoding. No custom training or downloading a training dataset.
- Keep model export/conversion tooling on the development machine; do not deploy an unnecessary training stack.
- Generate the model's own labels from its manifest. For COCO models, `cup` may cover a mug; walls, stairs, holes and glass are not guaranteed classes or detections. Never market this as detecting every hazard.

### 3. Build the live pipeline

Target modules, adapted to existing structure:

```text
app/vision/model.py       load once; preprocess; infer; normalize results
app/vision/service.py     newest-frame slot, one job/session, age/source checks
app/vision/tracking.py    lightweight matching, stable IDs and announcement policy
app/vision/router.py      mountable /vision and /vision/latest handlers
scripts/live_smoke.py     camera/file source and actual API smoke test
scripts/measure_live.py   sustained rate, age and drop/fault measurements
firmware/camera/          W11 automatic uploader + verified board configuration gate
firmware/feedback/        local sensing/actuation + telemetry/command adapter
qa/                      results and exact remaining blockers
```

These are your proposed owned paths; preserve an already-working equivalent. Canonical auth/frame ingest/status/database remain with the backend teammate. Add model dependencies via a coordinated small manifest change.

- Initial 640×480 capture, target **5 fresh detection results/s**. Measure actual throughput; no promised frame rate from a published benchmark.
- One newest pending frame per session and one inference job at a time; overwrite/drop obsolete pending frames. No unbounded queue. Model loads once, not on each frame.
- Capture identity: session, device, boot, sequence, frame ID, aligned capture time and source revision. Preserve image orientation; selfie mirroring must not reverse cues.
- Target capture-to-result p95 ≤500 ms during a 60 s run. Results older than 1000 ms cannot be spoken as current. These are engineering gates, not validated walking-safety thresholds.
- If live results stop for >1 s, show/speak a deduplicated live-unavailable state and suppress stale visual output. Do not automatically resume unsafe queued guidance or replace results with fixtures.
- Start/resume capture automatically; pause/stop/hide cancels capture/output and invalidates old results. Switching camera invalidates in-flight results and old tracks.
- Stable tracks/box association: ordinary speech after two consistent detections; 3 s cooldown per track/position; describe changes instead of narrating every frame. The sensor stop preempts all lower-priority output.
- Keep camera transport rate, model FPS, returned-result rate and capture age separate in metrics. A smooth video preview is not proof of live detection.

### 4. Supply the frontend/backend integration contract

Existing device/route endpoints remain. Required live semantics:

| Interface | Behavior |
| --- | --- |
| `POST /frame` | Raw JPEG plus authenticated session/device/frame/time metadata. Store newest eligible frame and feed active detector automatically. |
| `POST /vision` | Session/action ID plus `start|pause|resume|stop`; return authoritative live state/source revision. |
| `GET /vision/latest?session_id=...` | Latest fresh objects, track IDs, labels, normalized boxes, detector scores, frame/source identity, age, measured rate, status and stable event IDs. |
| `GET /status` | Include live vision state and feedback priority; not a separate competing controller. |
| `GET /time` | Server time for clock-offset/RTT checks, with allowed UI/device authentication. |

Use shared-cookie auth for the phone and a separate camera token for W11. Do not expose server/model/device secrets in browser code. Device-readable live start/stop state must use a device-authorized endpoint or polling response; do not assume firmware can call a UI-cookie-only endpoint.

Return fields: `frame_id`, `captured_ms`, `completed_ms`, `age_ms`, `source_revision`, `source=real|simulated|fixture`, `origin`, `status=live|stale|paused|unavailable`, `result_hz`, `objects`, optional `speech_event`. Objects have stable ID, label, software-derived image position and one agreed normalized box format. Model scores are not calibrated safety probabilities.

Front end polls latest results at up to 5 Hz while active and ignores older state/event IDs. Prefer existing event streaming if already functional; do not add it merely for style. Optional Gemini `/perception` is outside the automatic detector path and cannot block the live worker.

Preserve route state in the backend. Vision does not infer a safe turn or exact distance. A chair box and an ultrasonic echo are separate measurements unless a tested association exists.

### 5. Prepare hardware software without waiting for assembly

**W11:** verify exact PCB revision/vendor camera pin map, memory/toolchain settings and sensor connector. Never guess AI Thinker camera pins. Write bounded automatic JPEG uploads, frame/boot/sequence timestamps, buffer release, reconnect and selected-session handling. Record actual compile settings/results. Unknown board config is a clear blocker, not a fake success.

**DevKit:** GPIO18 TRIG; GPIO19 divided ECHO; GPIO23 switched buzzer; GPIO25 switched 3 V motor; optional GPIO26 second motor. Prepare nonblocking local sensor/feedback state machines and separate bounded network work. Local obstacle warnings survive internet loss. No remote command can disable the local warning loop.

Sample at 100 ms intervals, 10 µs TRIG, 30 ms echo timeout, median of three valid readings. Calibrate starting warning bands at 100/60/30 cm with 5 cm hysteresis. No echo is unknown, not clear.

One-motor patterns: left 200 ms ON; right 200 ON/200 OFF/200 ON; straight three 120 ms pulses with 120 ms gaps; stop 800 ms ON. Command IDs, session/generation, remaining TTL ≤1500 ms, ACK and deduplication prevent stale repeated turns. `cancel` cancels remote turns, never local alerts. On reboot/link loss cancel old remote cues; don't replay after recovery.

Physical circuit: motor regulated **3.0 V**, MOSFET/diode/decoupling and common ground; never GPIO-direct or 5 V. HC-SR04 ECHO needs the specified divider. Use `Outlook_Hardware_Wiring_Guide.md` for full connections. Humans perform rail measurements and assembly; you provide source/configuration and interpret logs. Do not claim physical validation from compiled code.

## Deadline priorities

Use actual remaining time. First prove a local live detector, then hosted phone-to-detector-to-phone performance. Integrate the W11 source when board facts/parts are available, leaving the final build hour for physical checks and release stabilization. Frontend and backend work proceed in parallel, not after this entire workstream finishes.

Cut optional Gemini, GPS import, voice input, second motor and elaborate dashboards before cutting continuous perception. A phone-camera fallback can prove software but must be labeled; it does not prove glasses operation. A snapshot-only fallback does not satisfy the live vision requirement. Do not change product claims to conceal a missed gate.

## Completion evidence

Record PASS/FAIL/BLOCKED/NOT RUN with actual source, device, commit, command and evidence:

1. Real webcam → automatic detector outputs for 60 s; moved/new/removed supported objects; no repeated clicks; actual rate and p50/p95/max age.
2. Hosted phone path works while the local Mac development server is stopped.
3. Network slowdown/inference overload causes bounded drops, not backlog; expired results cannot reach speech or route commands.
4. Pause/stop/source switch prevents old frame/track/event replay.
5. Stabilized speech does not flood; sensor stop interrupts route/object output.
6. Actual glasses W11 → deployed detector → iPhone/AirPods measured separately from webcam/phone tests.
7. Sensor/local motor and offline local alerts tested on physical hardware if available; otherwise explicitly blocked, never inferred from simulator.
8. Existing frontend/backend tests remain passing; document fixes and shared-interface changes.

Return a concise engineering handoff: owned files/commit, exact start/test/firmware commands, model artifact/config, measured performance, deployed URL or specific deployment blocker, integration instructions for the two teammates and remaining hardware requirements. Do not finish at a plan or a fabricated success report.

## Collaboration and Git

No duplicate frontend/backend rewrite. Do not modify shared entrypoints/schema/persistence without coordinating a small compatible patch. No resetting teammates' work, force-pushing, secret commits or account purchases. Use configured Git author identity; do not add Codex co-author trailers or rewrite human attribution. Preserve the team's tool workflow where required, but avoid another open-ended specification-approval cycle unless the human explicitly requires it.

## References for the reviewed plan

- [Pinned software branch snapshot](https://github.com/adhyannsingal/stride/tree/5cc61fde5f1b65764d5dc8f47aab28be52122aa1)
- [Reviewed Phase_1](https://github.com/adhyannsingal/stride/blob/5cc61fde5f1b65764d5dc8f47aab28be52122aa1/Phase_1)

This review examined the planning file and repository tree. It did not execute nonexistent application code or claim to review teammates' unpushed changes.
