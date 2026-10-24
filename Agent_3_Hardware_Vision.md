# Agent 3 — Stride hardware and live vision (Adhyann)

## Your assignment

Own the model, continuous inference service, firmware, physical integration and measured end-to-end evidence. Agent 1 owns **all backend application/device server code, shared contracts and deployment**. Agent 2 owns frontend, browser capture and speech playback. This replaces the previous numbering. Read `contracts/API.md`, `Stride_Live_Vision_Requirements.md` and `Stride_Hardware_Wiring_Guide.md`; use the electrical guide for actual wiring.

Implement your code now with real webcam images and simulated telemetry; assembly can wait for the parts. Human Adhyann performs physical checks, wiring and flashing. Your coding agent prepares source/configuration and tests; it cannot claim to have measured a rail or worn the glasses.

## Exclusive ownership

| You own | Do not implement |
| --- | --- |
| `app/vision/`: model load/preprocessing/decoding, newest-frame worker, tracking, vision router | Another FastAPI app, `/frame`, auth, DB/session engine or `/status` |
| `models/manifest.json`, `scripts/export_model.py`, `scripts/live_smoke.py`, `scripts/measure_live.py` | Frontend camera upload/overlays/speech or a second UI |
| `firmware/camera/`, `firmware/feedback/`, verified board configuration and ignored secrets | Server device queue, telemetry endpoints or ACK storage; Agent 1 owns `app/devices/` |
| `scripts/simulate_feedback.py`, `tests/vision/`, `tests/integration/`, `qa/vision-hardware.md`, `handoff/vision-hardware.md` | Shared schemas/settings/dependencies/deploy config; send Agent 1 exact requested changes |
| Wiring guide corrections, physical bring-up and final integration evidence | Optional Gemini implementation, route editor, cloud account setup or native iOS app |

Keep model binaries out of Git unless deliberately small/appropriate. Record download/export source, version, hash, class list, input/output layout and reproducible artifact setup. Agent 1 owns deployment wiring; you supply the model/runtime resource requirements and test the deployed result.

## Model and continuous service

1. Inspect existing code/branches first. At this review `main=905b2218a142be9b20696ba823db63444e9b5f91` and `software=5cc61fde5f1b65764d5dc8f47aab28be52122aa1` had planning files only. Do not assume unpushed teammate code is absent. Use existing working equivalents and preserve changes.
2. Choose one small pretrained YOLO detector and prove webcam inference immediately. OpenCV is optional capture/preprocessing support, not the detector. No custom training. Pin checkpoint/export/runtime, exact classes, letterbox/orientation/scaling, decoder and NMS. If exporting ONNX, compare original/exported detections on representative images. Record applicable model/license requirements rather than assuming unrestricted redistribution.
3. Model loads once. Keep one newest pending frame per session, one active inference job/session and a global concurrency bound appropriate for the host. Overwrite pending old work; no unbounded queue. Do not block FastAPI's event loop with CPU inference. One serving worker avoids duplicate process-local state/model copies.
4. Track stable class/box matches, require two consistent detections for ordinary announcements and a 3 s cooldown per track/position. Expire removed tracks; source revision/session changes clear matches. Emit candidate observations, not direct motor turns or frontend speech. Backend arbitrates events; frontend plays them.
5. Target 5 fresh results/s and capture-to-result p95 ≤500 ms over 60 seconds. Report actual rate, p50/p95/max age, drops and host resources; these are engineering targets, not safety claims. Reject current-scene output older than 1000 ms or unverifiable capture age. If no fresh output for >1 s, publish unavailable and clear stale objects; never replay old events after recovery.
6. Labels are limited to the selected model. `cup` may include a mug; glass, holes, stairs and walls may be absent or missed. Positions are camera-image left/center/right, not depth or a safe direction to walk. HC-SR04 distance is separate from any detected object's box.

## Seam supplied to Agent 1

Provide `app.vision.router.router` and `VisionService(settings)`; agree typed signatures in the shared contract immediately:

| Method | Meaning |
| --- | --- |
| `start()` / `close()` | App lifespan: load/start once and shut down bounded workers |
| `control(session_id, action, source_revision)` | Start/pause/resume/stop live processing; idempotency enforced through canonical action IDs |
| `offer_frame(frame)` | Nonblocking newest-frame handoff of already validated JPEG and metadata |
| `snapshot(session_id, now_ms)` | Current state/objects/metrics with age recomputed at read time |
| `invalidate(session_id, source_revision)` | Clear pending/current output/tracks; reject publication from retired in-flight work |

Agent 1 instantiates `app.state.vision`, mounts your router and calls your service from its one `/frame`. Use its auth/session dependencies. Internal frame record includes bytes, dimensions, session/device/boot/frame identity, sequence, source/origin/revision, aligned capture/receipt time and clock validity. Publish observations through an injected async callback; Agent 1 owns sighting persistence and output priority. Agree callback/result types before either side writes a competing adapter.

Your router supplies `POST /vision` and `GET /vision/latest?session_id=...`, using shared API schemas. Results include server/state/frame identity, source revision, captured/completed times, age, result rate, status, objects with stable track IDs, detector scores and normalized `[x_min,y_min,x_max,y_max]` boxes. Backend decorates with the centrally authorized speech event; raw candidate observations must not bypass obstacle priority. Do not create another `/status` or provider-specific camera endpoint.

## Firmware and physical sequence

**W11:** exact ESP32-S3/OV3660 PCB pinout is unknown. Require matching vendor/PCB revision evidence for D0–D7, XCLK/PCLK/VSYNC/HREF/SCCB/PWDN/RESET, flash/PSRAM and boot settings. Never use a guessed AI Thinker map. Prepare firmware with an explicit unconfigured-board failure until verified. Compile evidence is not camera hardware evidence.

Use the supplied camera ribbon and verified USB input. Start camera-only; pass 20 JPEG captures before adding upload. Post raw JPEG ≤1 MB automatically to Agent 1's `/frame`, with device-token auth and canonical metadata including `X-Source-Revision`. Verify TLS CA/time; no permanent insecure TLS workaround. Bound network work and always release camera buffers. Sync time/RTT; unsynced frames are diagnostic, not fresh live proof. Poll device-authorized `/devices/{id}/camera-state` for selected/active state and revision; pause or stop on inactive/unreachable state. No stored backlog, cross-session upload or replay on reconnect.

**DevKit:** GPIO18 TRIG; GPIO19 ECHO **through the guide's 1 kΩ top/2 kΩ bottom divider**; GPIO23 switched active piezo buzzer; GPIO25 protected 3 V motor, GPIO26 optional second channel. Verify supply/divider voltage against actual input limits before connection. Motor uses a measured regulated 3.0 V supply, MOSFET driver, flyback diode and suppression/common ground; never GPIO-direct or 5 V. Refer to the full guide for component ratings, power paths and exact circuit.

The sensor/alert loop must survive HTTP/TLS/internet failure: 100 ms ranging cycle, 10 µs trigger, bounded 30 ms echo timeout, median of 3 valid samples; initial calibration bands 100/60/30 cm, 5 cm hysteresis. Invalid/no echo is unknown, never clear. Boot outputs LOW. Network runs separately with bounded buffers/timeouts; local urgent warning preempts remote turns and cannot be remotely disabled.

Single-motor vocabulary: left 200 ms ON; right 200 ON/200 OFF/200 ON; straight three 120 ms pulses with 120 ms gaps; stop 800 ms ON plus buzzer. This is learned pulse coding, not physical directional localization. Do not silently replace with the optional two-motor patterns.

Use Agent 1's `/telemetry`, command polling and ACK routes. Validate session/device boot/generation/ID, deduplicate commands and subtract measured request elapsed time from server remaining TTL (maximum 1500 ms from creation). Cancel old remote cues on boot/link loss/pause and never replay them. Local alerts remain. Report accepted/completed/rejected/expired honestly; ACK alone cannot prove a physically vibrating motor.

Human assembly order: identify W11 → measure USB-derived rails → verify ECHO divider with safe DC/scope measurement → sensor only → switched buzzer → regulated motor/driver → camera network → combined load/heat test → insulated mounting/strain relief. W11 front of glasses, HC-SR04 beside it; DevKit/drivers at collar, motor wrist, dual-output USB bank pocket. Disconnect power before rewiring; avoid USB/external-rail backfeed. No fabricated board pinout or unsupervised navigation trial.

## Integration plan for all three agents

**Shared baseline:** create separate branches from current `main`: `stride/backend` (Agent 1), `stride/frontend` (Agent 2), `stride/hardware-vision` (Agent 3). Use the team's existing equivalents if active; don't reset or move uncommitted work. Each agent edits only its owned paths. Agent 1 owns shared files and integrates small commits every 45 minutes. No force-push, bulk directory replacement or speculative rewrite. Agent 1 publishes an integration SHA after each merge; others merge/rebase safely onto that baseline.

| Gate | Agent 1 — backend | Agent 2 — frontend | Agent 3 — you | Integration proof |
| --- | --- | --- | --- | --- |
| First 20 min available | Freeze shared schemas and service signatures; auth/session/health | UI shell/API adapter, explicit fixtures | Model smoke and importable service signatures; board evidence inventory | Same field names, ownership and runnable baseline |
| By 45 min | Mount service and accept `/frame`; deploy early | Automatic webcam capture and result rendering | Real webcam detector + simulator client | Real image produces live result without repeated clicks |
| By 90 min | Phone-reachable same-origin HTTPS, model/settings wired | Real iPhone upload, speech enable and polling | Measure hosted throughput/age and resource usage | Phone → hosted YOLO → phone, actual fresh detections |
| Next 1–2 h, within remaining budget | Route/memory, telemetry priority, expiring commands | Route controls, interruption, find/recall | Loss/slow-frame tests, simulated sensor + command/ACK | Route → cue → simulator; urgent alert cancels lower-priority output |
| Last build hour | Bind real devices; diagnose server/logs | Select W11; observe speech/status, no browser duplicate upload | Assemble/flash incrementally; verify actual local alerts and W11 | Glasses → host → iPhone/AirPods, actual motor and offline local warning |
| Final 30 min of build | Freeze/redeploy and verify README | Rehearse accessible flow/video script | Publish measured integration report and hardware limits | Stable release SHA; reserve separate hour for recording/submission |

These gates use the **actual remaining time**, not a new six-hour promise. Start model/webcam/server work in parallel. If parts are absent, continue using explicit simulation and record physical tests blocked. A phone/webcam fallback proves software, not glasses operation. Optional Gemini/GPS/voice input/second motor/dashboard polish are cut before live vision.

**Merge order:** (1) Agent 1 contracts/skeleton, (2) your model/service/router plus Agent 1's mounting patch, (3) Agent 2 API-connected UI, (4) backend device policy + your simulator, (5) firmware/real devices. Frontend and model development proceed independently on fixtures/direct tests while those small merges happen; nobody waits for the entire previous workstream to finish.

**Runtime configuration:** Agent 1 owns one `.env.example`/settings/deploy config and names for app access code, database, model path, simulation toggle, device tokens and optional Gemini key. You request model/runtime settings and consume backend-provided exact names; do not invent a second environment convention. Firmware has ignored private Wi-Fi/token/session/CA config plus committed examples with no secret values. Agent 2 uses same-origin APIs and never receives device/provider secrets.

**Handoffs:** each agent commits `handoff/backend.md`, `handoff/frontend.md` or `handoff/vision-hardware.md`: commit, owned files, exact run/test commands, interface changes requested, actual passing checks and blockers. Agent 1 alone applies shared-file patches. If two agents need an API change, agree one updated example/schema before coding it; do not add compatibility endpoints in parallel.

## Final acceptance you coordinate

Record PASS/FAIL/BLOCKED/NOT RUN, actual source/device, release SHA and evidence in `qa/vision-hardware.md`:

1. 60 s real continuous detection: rate, p50/p95/max capture-to-result age and dropped frames; moved/new/removed supported objects.
2. Slow inference/network → bounded drops, no queue growth; results older than 1000 ms never become current-scene speech.
3. Pause/stop/source switch → no late frame, old track or duplicate event replay.
4. Checked-route instruction → one expiring command → one motor pattern; Repeat doesn't advance checkpoint; urgent local alert wins.
5. Unplug internet → local HC-SR04 buzzer/motor still work; remote turns expire; stale cloud output unavailable. Don't claim remote speech tracks an offline sensor.
6. Actual W11 glasses feed → deployed detector → iPhone/AirPods, measured separately from laptop/phone source. Stop the Mac development server; final runtime must still work.
7. Sensor/driver voltage, mounting, heat and sustained powered checks physically observed. Missing W11 pin map or missing parts are explicit blockers, not simulated passes.

Use a checked controlled route with a sighted spotter. The product targets navigation assistance; the prototype is not validated for independent walking or road crossings. Deliver reproducible launch/model/firmware instructions and actual results. Use configured Git identity; no Codex co-author trailer, secret commits, account purchases or unrelated task expansion.

## Next 2–3 hours: software demo before parts arrive

Use the **Mac webcam as capture source**, hosted inference as planned, and the iPhone solely as viewer/AirPods playback for the same session. Agent 2 owns that browser capture/viewer implementation; you supply the detector and measured evidence, not a second uploader UI. `scripts/live_smoke.py` may upload webcam frames as a standalone diagnostic using an explicitly registered/bound source; stop browser capture before using it. It must not compete with another selected producer. Do not claim a command exists until implemented and tested.

The software demo is Mac webcam → hosted model → phone results/audio. Keep the Mac capture tab foreground and label the source. The laptop supplies images for this development demo; final W11 operation still requires a separate laptop-independent test. The phone must join as viewer without taking over camera ownership.

While waiting for the expected parts in 2–3 hours: finish real model inference, both firmware projects, ignored configuration examples, simulator command/ACK tests and the physical bring-up checklist. As soon as parts arrive, start staged bring-up rather than waiting for the last minutes: identify/verify W11 and run camera-only; test sensor-only; add buzzer; add protected 3 V motor; then bind both boards to the hosted session. Missing exact W11 board data blocks only that camera configuration, not sensor firmware or the software demo.

Firmware deliverables must contain actual compilable source, not just comments:

- `firmware/camera/`: camera initialization using verified board config, automatic JPEG capture/upload, buffer release, TLS/time synchronization, active-source polling, timestamps/revision/sequence and bounded reconnect. Include board/core/PSRAM settings and exact compile/flash steps once verified.
- `firmware/feedback/`: HC-SR04 trigger/echo sampling and valid/timeout handling; filtered distance bands/hysteresis; local buzzer and motor patterns; priority/preemption; separate bounded networking; telemetry, expiring command polling/deduplication and ACKs; outputs off at boot. Include exact DevKit compile/flash steps and sensor/buzzer/motor self-test modes.
- Both projects: committed configuration examples, ignored private secrets, actual compile results for verified targets, and explicitly blocked camera configuration when its pinout is still unknown. A successful compile does not establish physical operation.
