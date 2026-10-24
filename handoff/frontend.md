# STRIDE Phase 5 frontend handoff

Implementation prepared on `feature/frontend`, based on `9c78818ec95004a4bdfaf491ed8352dec9fd6c3b`. Publishing this frontend-only commit was explicitly authorized after validation. No merge, rebase or force-update is authorized. This supersedes the old src/lib handoff.

Executable backend reference: main `d6ebcb991d8f0644579a3ac4ff40fa04122a80a2`, `backend_phase3/` (Phase 4). Software `4afb50660612ce627938620f62c558d0aa858bb8` places Phase 4 in `backend_phase3 2/`. Compared its actual models, route/device models, auth, vision and navigation to main: identical. Main additionally preserves detector memory lifespan hooks. Backend, vision, firmware, shared contracts and secrets were not edited or merged.

## Merge readiness update

The confirmed lost-response recovery blocker is fixed. An uncertain vision request is resolved using its original action ID and payload before validating the next action. Pause/Stop can follow a lost successful Start, and Stop pressed during an in-flight action is queued. An explicit retry control remains accessible even when polling already shows the terminal state. Five actual-backend browser regressions cover these cases.

Root `.gitignore` now matches main, preserving its secret/model/database exclusions and removing the add/add conflict. A temporary commit/tree was used for `git merge-tree --write-tree` verification only; no branch ref changed. The combined source snapshot passed the checks below. Use the new `stride-frontend-merge-ready.patch`, which supersedes the earlier patch.

To apply from a clean `feature/frontend` checkout at 9c78818:

```sh
git apply --check /path/to/stride-frontend-merge-ready.patch
git apply /path/to/stride-frontend-merge-ready.patch
cd frontend
npx pnpm@10.34.3 install --frozen-lockfile
npx pnpm@10.34.3 exec tsc --noEmit
npx pnpm@10.34.3 test
npx pnpm@10.34.3 run build
```

Review and commit only the changed text/source files, then push feature/frontend and open/review its PR into main. Do not stage the unchanged PNG files as LFS pointers. Recheck against new main commits if teammates push after this snapshot.

## Implemented

- One bounded speech scheduler (8 waiting events, 4,096 consumed IDs per session, fails closed at capacity). Priority danger → fault → route → observation → requested information. Revalidates deadlines, session, route revision, vision generation/source while queued and speaking. Cancel invalidates callbacks before browser cancellation. No synthetic object narration. Danger deduplication uses hold episodes rather than each poll.
- Camera loop owns one canvas, one upload, bounded JPEG (longest side 640, ≤512 KiB), monotonic sequence and unique boot/frame IDs. Captures timestamp before encoding, aborts on stop, rechecks generation/consent after asynchronous work, releases tracks and reports permission/upload failures. Up to 5 FPS is a target, not measured detector performance.
- Browser capture requires explicit Start this camera, consent and an operator-confirmed dedicated single-producer session. Uses source_revision returned by the server, never invents ownership. Viewer/glasses modes never open the camera. Another observed producer or source/generation change stops this producer.
- Separate nonoverlapping, abortable vision and navigation/device polls, backoff and lifecycle invalidation. Vision freshness ages locally between responses and includes request elapsed time conservatively. Hidden pages stop local capture/audio and polling; capture requires another explicit gesture.
- Terminal vision Stop never offers Start on the same session. Failed stop is visibly unconfirmed; local capture/audio stop regardless. Navigation remains server-authoritative. Uncertain mutations retain their exact payload and ID for an explicit retry; 409 restores authoritative progress. Stop remains locally available during a pending route action and requests server Stop after it settles.
- Device danger cannot be masked by navigation clear. Stale/invalid/unavailable readings become unknown. Historical readings stay diagnostic. Firmware command queues are never consumed by the browser.
- Real login clears preview data and old session state. Tokens are not persisted; inputs clear after submission. Cookie-based requests include credentials and no-store. Time sampling converts route expiry into a conservative monotonic deadline. HTTP errors preserve backend detail and add actionable instructions.
- Removed unused mock dashboard from App.tsx. Landing component, animation logic, global index.css, and image bytes are unchanged. Dashboard text size, safe areas, Stop contrast and mobile navigation improved. Inputs have accessible names. Replaced only dashboard dropdowns with styled native controls: Astra's dropdown had unlabeled comboboxes, reused IDs and document-wide keyboard interception.
- Existing direct dependency versions pinned; regenerated lock with older Babel/parser and cookie-parser overrides because the original lock failed the execution environment's minimum-release-age policy. No policy was disabled. No new runtime package added.

## Run

Node 24 was tested. From `frontend/`:

```sh
npx pnpm@10.34.3 install --frozen-lockfile
npx pnpm@10.34.3 exec tsc --noEmit
npx pnpm@10.34.3 test
npx pnpm@10.34.3 run build
npx pnpm@10.34.3 run dev --host 127.0.0.1
```

Development UI: http://127.0.0.1:8443. Vite proxies implemented API paths to http://127.0.0.1:8000; override with server-only `STRIDE_DEV_API_TARGET`. Leave `VITE_STRIDE_API_URL` unset for same-origin requests. Start the existing backend separately using its owner's instructions. Provision UI session credentials in backend environment. Local cookie testing needs `STRIDE_LOCAL_DEV=true` on loopback; do not use this configuration as a hosted security setup.

The production build is static output only. Backend/deployment owner must route API paths and frontend assets through ONE HTTPS origin. Do not assume cross-site cookies work with SameSite=strict; do not weaken cookie security. Validate forwarded scheme/origin and persistent SQLite storage on the actual host.

## Contract matrix: verified against actual HTTP backend fixture

| Endpoint | Actual request/response used |
|---|---|
| GET /health | `{status:"ok"}`; no invented readiness fields |
| GET /time | `{server_ms}` for route expiry normalization |
| POST /auth/session | `{session_id,session_token}` → HttpOnly session cookie, expires_ms |
| POST /frame | Multipart file JPEG plus session_id/device_id/boot_id/frame_id/sequence/captured_ms/source/origin/source_revision → 202 receipt |
| POST /vision | session_id/action_id/action/expected_generation → generation/state_seq/source_revision; Stop terminal |
| GET /vision/latest | session_id query; bbox XYXY, age_ms, generation/state_seq/source_revision and optional speech_event |
| GET /routes | session_id → routes with checked, demo_fixture, checkpoints |
| POST /route | start includes route_id; subsequent actions navigation_id/expected_revision; idempotent action_id |
| GET /memory | session_id → navigation/history/sightings, returned_at; historical records only |
| POST /device/pair | device_id/session_id using UI cookie; allowlisted device only |
| GET /device/status | device_id/session_id; separate freshness, validity, current/historical measurements, source and haptic audit |

Error envelope is `{error:{code,message,fields?}}`. No `/auth`, `/sessions`, camera selection or `/perception` calls are invented. Existing firmware-only command and ACK APIs remain outside the frontend.

## Remaining backend dependencies and limits

1. **Camera ownership:** backend does not implement the planned producer-selection endpoint. Development confirmation is not server-enforced ownership. Use only one producer/session; no safe multi-producer switching is claimed.
2. **Object speech:** YOLO returns speech_event=null. UI displays detections but does not synthesize object announcements. Backend must supply stabilized, authorized events. Remote current-scene speech also needs trustworthy capture-to-result freshness; server receipt age alone is insufficient. The adapter conservatively requires aligned capture metadata for observation speech.
3. **Session restart:** operator provisions a fresh session after terminal vision Stop. No public session-creation endpoint exists.
4. **Hosting:** same-origin local proxy tested; deployed HTTPS, secure cookies and remote camera transport not tested.
5. **Hardware/iPhone:** local ESP32 alerts remain independent. No ESP32, motor, W11, iPhone Safari/VoiceOver, AirPods routing, physical haptics, latency or independent navigation acceptance was performed. Browser speech uses system output, cannot prove AirPods routing.
6. **Pause/exit:** hiding/exiting stops this client's capture and speech; it does not prove global backend or hardware Stop. Use the explicit Stop control and verify its response. Disconnected UI cannot confirm remote actions.
7. Browser tests use synthetic routes and a temporary database, not a physically verified route. No actual YOLO model was loaded. Preview remains explicitly simulated. Full accessibility compliance is not claimed.

## Changed files

Modified: .gitignore; frontend/package.json, pnpm-lock.yaml, tsconfig.json, vite.config.ts; src/App.tsx; src/app/{StrideApp.tsx,api.ts,controllers.ts,app.css}; handoff/frontend.md; qa/frontend.md.

Created: frontend/pnpm-workspace.yaml; src/app/{policy.ts,AccessibleSelect.tsx}; tests/{api.test.ts,controllers.test.ts,backend_fixture.py,contract-live.ts,smoke.mjs,recovery.mjs,run_acceptance.py}. A portable handoff patch is supplied separately.

The repository incorrectly applies LFS filters to already committed raw PNGs. Git may report them dirty after checkout; all five PNG files are byte-identical to HEAD and are excluded from the patch. Do not stage those files as LFS pointers during this change.
