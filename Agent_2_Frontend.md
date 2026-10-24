# Agent 2 — Stride frontend

## Your assignment

Build the accessible phone interface, browser camera pipeline and spoken feedback. Agent 1 owns backend, shared contracts, server device logic and deployment. Agent 3 (Adhyann) owns hardware, firmware and live YOLO. These briefs replace the previous assignment where Agent 2 did devices and Agent 3 did UI. Read `contracts/API.md`, `Stride_Live_Vision_Requirements.md` and Agent 3's integration section.

Implement now, end to end. Navigation is primary: a checked guided route, immediate obstacle status, spoken instructions and directional motor cues. Continuous objects-ahead awareness starts once and keeps updating while walking. Find/recall supports navigation; it is not the whole product. This prototype uses explicit checkpoint confirmation and cannot infer a safe path or guarantee detection of every obstacle.

## Exclusive ownership

- **Own:** `web/` including `index.html`, styles, API client, camera loop, overlays, speech scheduler, route UI and local development fixtures; `tests/browser/`; `qa/frontend.md`; `handoff/frontend.md`; `submission/demo-script.md`.
- **Do not edit:** `app/`, `firmware/`, `contracts/`, dependency manifests, deployment config or root README. Give Agent 1 a concise README patch/request in your handoff. Agent 1 serves your existing static app; do not create a second backend, detector, cloud account or native iOS application.
- Prefer the current working frontend if one exists; otherwise vanilla HTML/CSS/JavaScript. Do not spend the sprint on a framework migration. All backend calls go through `web/api.js` so fixtures and real APIs share one adapter.

## Build these flows

1. **Connect:** open the same-origin HTTPS app, enter access code, create/select session and devices, display source and health, tap to enable speech and request camera permission. Offer webcam/phone camera for development and W11 for glasses operation. A simulator remains visibly labeled.
2. **Guided route:** select/create a short checked route, Start, Confirm checkpoint, Repeat, Pause/Resume and Stop. Backend owns progress; render authoritative state rather than incrementing locally. Repeat never confirms. Pause/Stop are always easy to reach. Do not require GPS or automatic localization.
3. **Live view:** Start navigation activates `/vision` once. With browser source selected, automatically capture/upload current JPEGs; with W11 selected, stop browser uploads and consume the same results. Render actual result age/rate, camera origin, source, status and optional boxes. Repeated Analyze clicks cannot be the main vision loop.
4. **Speech:** speak concise route instructions, stabilized objects-ahead events and faults through iPhone audio/AirPods. Use stable backend event IDs, priority and expiry. Repeat is a new authorized event, not replay of every poll. Do not narrate every frame.
5. **Find/recall:** search supported detector labels, show not-found honestly, request optional Gemini only when backend says available, and display last-seen age/checkpoint/source. A remembered sighting is not a current object location. Typed input is sufficient; voice recognition is stretch.
6. **Feedback health:** show distance as the separate sensor reading, freshness, local alert and command/ACK status. Never label UI animation or a simulated ACK as a real vibration. A single 3 V motor represents learned pulse patterns, not physical left/right localization.

## Implement in this order

- First 20 minutes of actual remaining time: shell, large labeled controls and API adapter using explicit fixtures. Publish to Agent 1 the static entrypoint and endpoints needed. Fixtures must be selectable development mode, never silent fallback after an API error.
- First 45 minutes: real webcam capture, Start/Pause/Stop loop, a user-gesture speech test and mocked live payload rendering. Integrate Agent 1's real session/auth endpoints as soon as available.
- By the first 90-minute gate: iPhone → hosted `/frame` → real YOLO → `/vision/latest` → iPhone speech, with Agent 1/3. A local preview alone does not pass. Use actual available hosting; report access blockers promptly.
- Next: route controls/memory, sensor interruption, stale-state handling and actual AirPods testing. Keep a runnable vertical slice throughout; do not wait for physical hardware.
- Final hardware window: select W11, verify browser capture stops, monitor real detections/telemetry and record device observations while Agent 3 assembles. You do no wiring/soldering/flashing.

The original sprint budget was six hours plus one hour recording/submission. Confirm remaining time and scale the sequence; no new six-hour clock. Cut optional features before core integration.

## Exact frontend integration rules

Use same-origin cookies; no API/device/provider tokens in JavaScript. Agent 1 owns `contracts/API.md` and endpoint changes. Use its exact fixtures/response schemas; propose a small contract change rather than independently renaming fields. Poll `/status?session_id=...` for route/feedback and `/vision/latest?session_id=...` up to 5 Hz while active. Avoid overlapping polling requests; back off on failure and abort on pause/stop/hide. Render only monotonically current state/revision/frame identity; order by server sequence, not response arrival.

Camera upload is raw `image/jpeg`, not multipart/base64. Start at 640×480, at most 5 uploads/s pending measured rate; keep **one request in flight** and drop obsolete work. Required headers from the shared contract: `X-Session-Id`, `X-Device-Id`, `X-Boot-Id`, `X-Frame-Id`, `X-Sequence`, `X-Captured-Ms`, `X-Clock-Synced`, `X-Source-Revision`. Agent 1 binds the browser camera identity during session setup. Use `/time` plus request RTT to align capture timestamps; cannot establish reliable age → expose unavailable, not false live status.

Prefer rear camera with `facingMode: {ideal: 'environment'}`; support available-device selection on Mac. Capture original unmirrored pixels. Preview mirroring must not reverse cue semantics. Agree one normalized `[x_min,y_min,x_max,y_max]` format in `[0,1]`, relative to the decoded upright image. Preserve aspect ratio when drawing overlays; boxes describe image location, not free walking space.

On source switch, pause/stop or page hide: cancel pending requests, stop tracks/timers as appropriate, clear boxes/tracks and pending observation speech, and invalidate local generation. Request backend control/invalidation too. Network failure may prevent server cancellation: show disconnected and suppress local stale output immediately; never claim W11 stopped remotely without confirmation. Resume explicitly. Ignore late responses from the old session/revision even if their request succeeded.

## Speech and AirPods

Use browser `speechSynthesis` with a user-gesture enable/test control. AirPods Pro 3 pair with the iPhone through normal Bluetooth/iOS audio selection; the web app cannot force their output route. Test the actual iPhone 14 and AirPods, keep the page foreground and disclose any platform interruption. Do not depend on the browser Vibration API: physical direction cues come from DevKit.

Agent 3 stabilizes detections; Agent 1 authorizes/deduplicates events; **you play them**. Do not independently generate another announcement from every box. Maintain a set of consumed event IDs across both polled endpoints within the session, recheck generation, expiry, source revision and current alert priority immediately before playback. Recompute age using aligned time; a result fresh at receipt can expire while queued. Live frame age >1000 ms is unspeakable. Clear old visual output when no fresh results arrive for >1 s and announce one deduplicated interruption.

Priority: urgent obstacle/stop > fault > route > observation. Higher-priority events cancel current lower-priority utterances. Since `speechSynthesis.cancel()` clears the browser queue, keep your own bounded scheduler. Drop expired low-priority events rather than flushing them after recovery. Local physical alerts remain independent; cloud-delayed speech is not guaranteed simultaneous with the sensor.

No LiDAR on standard iPhone 14. Normal speech is required; head-tracked/world-anchored sound is not part of the six-hour implementation. No spoken claim that a path is clear from missing detections.

## Acceptance and handoff

Test permission denial, no camera, front/rear orientation, session/source switch with late responses, Start once continuous operation, duplicate poll/event IDs, expired queued speech, urgent interruption, offline/stale state, manual checkpoint confirmation, Repeat and Pause/Stop. Include keyboard/focus/VoiceOver labels, large touch targets, readable contrast and actual iPhone/AirPods playback. Record browser/device and real versus fixture source.

Deliver `handoff/frontend.md`: files/commit, exact local preview and real backend setup, implemented flows, API expectations, actual device results and blockers. Add focused browser tests if the harness is available and useful; do not claim physical audio from a mocked test. Give Agent 1 README updates and Agent 3 a short end-to-end rehearsal checklist. Use configured Git author identity, no Codex attribution, no force-push or secret commits.
