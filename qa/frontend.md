# Frontend QA (Agent 2)

Branch `feature/frontend`. Primary app: `frontend/` (React/TS Figma import).
Environment: macOS, Node 25, `npx pnpm@10.34.3`, Google Chrome (headless).

## Automated checks (run this session)

```bash
cd frontend && npx pnpm@10.34.3 install --frozen-lockfile   # 264 pkgs, exit 0
cd frontend && npx pnpm@10.34.3 exec tsc --noEmit           # exit 0
cd frontend && npx pnpm@10.34.3 run build                   # exit 0, 25 modules
node --experimental-strip-types tests/browser/controllers.test.ts  # 12/12
```

| ID | Check | Result |
| --- | --- | --- |
| C01 | route start → guiding @0, emits speech event | pass |
| C02 | confirm advances; repeat does not advance | pass |
| C03 | final confirm completes once, no overflow | pass |
| C04 | pause/resume/stop transitions | pass |
| C05 | vision paused until start, live after | pass |
| C06 | camera selection bumps source_revision, clears results | pass |
| C07 | live box canonical xyxy, min<max, 0..1 | pass |
| C08 | speech dedupe by event_id | pass |
| C09 | expired event dropped + blocked from replay | pass |
| C10 | priority urgent>fault>route>observation | pass |
| C11 | stale live observation (age>1000ms) unspeakable | pass |
| C12 | resetForSource clears consumed ids | pass |

## Build + boot

- `tsc --noEmit`: exit 0 — Astra component prop types match the wiring.
- `pnpm run build`: exit 0 — 25 modules (7 new lib/component modules over the
  17-module baseline import), dist/ emitted.
- Headless Chrome on built `dist/`: Landing renders hero title "Your next step.",
  "Open STRIDE", `brand-mark`, Astra-styled Button; no app JS errors.

## Appearance-intact evidence

- `src/index.css` is byte-identical to the imported original (`diff` clean vs
  `HEAD:frontend/src/index.css`).
- Landing hero/section copy unchanged (extracted verbatim into `Landing.tsx`).

## Honesty / correctness checks (code-verified)

- No invented distances: object lines show `label · position` + detector score;
  the "8 metres" string is gone from the awareness panel.
- No AirPods claim: device summary shows "Browser speech ready/off/unsupported".
- Simulation explicit: provider label reads "Simulation (fixtures)" in fixture
  mode; mode is user-selected; real-mode errors surface in `state.lastError`,
  never a silent fixture fallback.
- Consent gate: browser capture requires Browser source + consent + explicit
  gesture; revocation calls `camera.revokeConsent()` and clears pending vision.
- Glasses mode: `setCameraSource('glasses')` stops any stream and the capture
  loop only starts for `source === 'browser'` — W11 path never calls getUserMedia.

## Manual device matrix (to run on real hardware — not yet executed)

- [ ] Permission denied / no camera → clear message, no crash.
- [ ] Mobile layout on iPhone 14 (portrait); large touch targets; VoiceOver labels.
- [ ] Session/source switch with late responses ignored (revision guard).
- [ ] Start once → continuous capture without repeated clicks.
- [ ] Duplicate poll / repeated event IDs spoken once.
- [ ] Expired queued speech dropped; urgent interrupt cancels current utterance.
- [ ] Offline/stale (>1s) → live vision unavailable, overlays cleared.
- [ ] Real iPhone/AirPods playback; record browser/device versions.

## Known gaps

- Live phone→hosted YOLO→phone and W11 transport unverified (integration gates).
- Mobile layout verified only via desktop headless DOM, not a physical phone.
