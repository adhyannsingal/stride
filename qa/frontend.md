# Phase 5 frontend QA — 2026-10-24

Baseline feature/frontend 9c78818; backend main d6ebcb9, unchanged. Linux, Node 24.22.1, Python 3.12.14, pnpm 10.34.3. Chromium 134.0.6998.35 via Playwright 1.51.1.

## Executed results

- Frozen install: passed (265 packages). CI=true used only because the environment had no interactive terminal when replacing a pnpm 11 install with requested pnpm 10.
- TypeScript: `npx pnpm@10.34.3 exec tsc --noEmit`, exit 0.
- Production build: `npx pnpm@10.34.3 run build`, exit 0, 23 modules.
- Node regression tests: 55 passed, 0 failed/skipped. `npx pnpm@10.34.3 test`.
- Actual HTTP checks: 13 passed through Vite proxy into unmodified FastAPI. Cookie exchange, checked routes, idempotent confirm, stale revision conflict, memory, multipart JPEG, vision lifecycle, pairing/status, unknown sensor hold, Stop.
- Browser workflow: 15 checks passed against actual FastAPI with a temporary database and synthetic routes. Landing, explicit preview, confirm/repeat, Stop across tabs, HttpOnly cookie, fixture clearing, checked/unchecked route controls, route lifecycle, terminal vision, pairing error, blocked confirmation, memory empty state, large text/dark theme, session cleanup, 390px portrait and 1440px desktop reflow, no page JS errors.
- Visual inspection: large-text mobile Devices view examined; mobile tabs adjusted to two columns for large text to keep labels distinct. No homepage visual edits.
- Preservation checks: landing component/animation source unchanged; index.css and public PNG bytes equal baseline. No backend/vision/firmware changes.

## Test coverage

Speech: enable gesture, dedupe, queued/playback expiration, urgent and fault preemption, priority ordering, invalidation, bounded queue, canceled callbacks, observation disable, explicit session reset.
Camera: consent/gesture/role/single-producer gates, one in-flight upload, slow request, correct source revision, metadata, revocation, late permission, track cleanup, permission denial, upload error.
Policy/API: current freshness, expired/paused/missing-age suppression, generation/state/source ordering, terminal stop, absence of fabricated speech, aligned capture gate, route validation, conservative obstacle precedence, uncertain payload+ID retention, poll cancellation/backoff, cookie requests, multipart boundary and HTTP errors 401/403/409/413/415/422/429/503.

## Reproduce actual backend/browser acceptance

Prepare the backend checkout and its development Python requirements separately. Install Playwright/browser for the smoke client if needed. From frontend:

```sh
STRIDE_BACKEND_CHECKOUT=/absolute/path/to/backend-checkout \
PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs \
/path/to/backend-venv/bin/python tests/run_acceptance.py
```

The runner starts backend_fixture.py and Vite, runs contract-live.ts, restarts the temporary backend database, runs smoke.mjs and tears down both processes. Fixture credentials are test-only literals and no external accounts/devices are contacted. Backend fixture explicitly labels its route verification synthetic; never use it for walking.

## Not verified / limitations

No physical camera permission or capture, hosted YOLO, iPhone Safari/VoiceOver, audible AirPods phrase, real ESP32 exchange, motor movement or walking safety test. Fake media and synthesis interfaces cover controller behavior only. The browser smoke does not establish accessibility conformance. Five-Hz polling/capture is a configured ceiling, not measured inference throughput. The consolidated Phase 4 backend suite was rerun on the combined snapshot: 261 passed, 1 real-detector integration test skipped, 1 Starlette TestClient HTTPX deprecation warning (20.81 seconds). Historical standalone Phase 1/2 suites were not rerun.

Initial smoke exposed missing accessible input names, now fixed. Initial environment browser download failed; the alternate installed Chromium 134 completed the smoke. Original dependency lock failed minimum-release-age checks; compatible older transitive overrides and exact baseline direct versions were used, without relaxing policy. Existing Astra transitive peer/deprecation warnings remain; compilation/build and tested flows pass.

## Final merge verification

Current remote refs rechecked: frontend 9c78818, main d6ebcb9, software 4afb506. Software is already an ancestor of main.

- Root ignore conflict resolved by preserving main's exact ignore rules.
- `git merge-tree --write-tree` with a temporary frontend snapshot: exit 0, no conflicts. No branch ref updated.
- Executed on the combined snapshot: TypeScript exit 0; Vite production build exit 0 (23 modules); 55/55 unit regressions; 13/13 actual HTTP checks; 15/15 existing browser checks plus 5/5 new network recovery regressions; 261 backend tests passed, 1 real-detector test skipped.
- Recovery regressions intercept requests in Chromium while FastAPI runs normally: lost successful Start followed by Stop; lost successful Pause followed by Stop; Resume never reaching server followed by Stop; lost successful Stop then exact-ID retry; Stop queued during delayed Start. Replayed payloads and action IDs are asserted identical.
- Earlier patch is superseded. No known merge-blocking issue remains in the tested scope. This is not a claim that every possible bug or physical-device dependency has been eliminated.
