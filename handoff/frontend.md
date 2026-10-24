# Frontend handoff (Agent 2)

Owner: Agent 2 (frontend). Branch: `frontend`. Author: configured Git identity.

## What exists

A runnable vanilla HTML/CSS/JS frontend under `web/`, built against
`contracts/API.md` and `contracts/examples.json`. No framework, no build step,
no plugin toolchain. All backend calls go through one adapter so fixtures and
the real backend share a single code path.

| File | Role |
| --- | --- |
| `web/index.html` | Accessible shell: connect, role, speech, live view, route, feedback, find. Large touch targets, skip link, ARIA live regions. Deliberately plain so the Figma Make design can be layered on later without restructuring. |
| `web/app.css` | Base styles: high contrast, ≥48px targets, visible focus, reduced-motion support. |
| `web/api.js` | Single API adapter. Fixture vs real mode, same-origin cookie auth, `/time`+RTT clock alignment, raw `image/jpeg` frame upload with contract headers. |
| `web/fixtures.js` | Explicit, selectable dev fixtures mirroring contract shapes. Route + vision state machines. Never a silent fallback. |
| `web/speech.js` | Bounded priority speech scheduler. Dedupe by `event_id` across both poll sources, priority preemption, expiry/age rechecks at playback, strict 1000 ms live cutoff. |
| `web/camera.js` | Capture loop. Explicit producer gesture, 640×480, one request in flight, generation invalidation, cancel on pause/stop/hide. Unmirrored captured pixels. |
| `tests/browser/logic.test.mjs` | Headless Node tests for the pure logic (fixtures + scheduler). |

## Run it

Fixtures mode (no backend needed):

```bash
cd web
python3 -m http.server 8099
# open http://127.0.0.1:8099/  (Mode = Fixtures, click Connect)
```

Against the real backend: Agent 1 serves `web/` as same-origin static files so
the auth cookie and API share an origin. Select Mode = Real, set the access
code, Connect.

Run the logic tests:

```bash
node tests/browser/logic.test.mjs   # 12 checks, exit 0
```

## Verified this session

- `node --check` passes for all five modules (Node v25).
- `tests/browser/logic.test.mjs`: 12/12 checks pass (route start/confirm/repeat/
  complete semantics, pause/resume/stop, vision paused→live, source-revision
  bump clears results, canonical xyxy box, speech dedupe, expired drop, priority
  order, stale-observation unspeakable, source reset).
- Static serving: `index.html` + all 5 modules return HTTP 200.
- Headless Chrome boot: ES module graph loads and executes (`setRole` sets
  `data-role="viewer"` and the role label from JS); no SyntaxError/ReferenceError/
  module-load failures.

NOT verified (needs real devices / backend): actual AirPods playback, iPhone 14
behavior, live phone→hosted YOLO→phone path, W11 transport.

## Flows implemented

1. Connect: mode select, base URL, access code, join-or-create session, health dot.
2. Role: Viewer (default, never touches camera) vs Camera source (getUserMedia
   only after the explicit "Use this device's camera" gesture).
3. Live view: Start navigation activates `/vision` once; camera role uploads
   automatically; metrics show status/rate/age/origin. Boxes overlay with a
   stale guard (>1000 ms clears).
4. Guided route: start/confirm/repeat/pause/resume/stop. Renders authoritative
   server route state; never increments locally. Repeat never confirms.
5. Speech: user-gesture enable/test; bounded priority scheduler plays
   backend-authorized events once.
6. Find/recall + feedback health panels.

## Expectations of the backend (requests for Agent 1)

The `software` branch backend currently implements `/health`, `/time`
(`{server_ms}`), and `POST /frame`. To light up the full frontend it needs the
contract endpoints: `/auth`, `POST /sessions`, `POST /sessions/{id}/camera`,
`GET /routes`, `POST /route`, `GET /status`, `POST /vision`,
`GET /vision/latest`, `POST /perception`, `GET /memory`.

**Contract divergence to resolve (Agent 1 owns the call):** the contract and
this frontend use raw `Content-Type: image/jpeg` for `POST /frame` with the
`X-*` headers. The current `software`-branch `/frame` parses
`multipart/form-data`. Please either (a) accept raw `image/jpeg` per
`contracts/API.md`, or (b) propose a contract change; the frontend will follow
the contract once decided. The adapter changes in one place (`web/api.js`
`uploadFrame`).

Minor: this frontend reads `/time` as `{server_ms}` (software branch) and also
accepts `{server_time_ms}`.

## README patch request for Agent 1

Add a "Frontend (web/)" run section: serve `web/` as same-origin static files;
fixtures mode works standalone via `python3 -m http.server` from `web/`.

## Rehearsal checklist for Agent 3

Two-client demo: Mac = Camera source (grant webcam, Start navigation), iPhone =
Viewer/audio joining the same session ID (Enable audio, select AirPods). Mac
uploads; phone speaks. Verify: viewer never calls getUserMedia; refreshing the
viewer stops only its own polling; explicit Stop is global; on W11 selection the
Mac upload stops and source_revision increments.
