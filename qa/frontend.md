# Frontend QA (Agent 2)

Branch `frontend`. Scope: `web/` and `tests/browser/`. Environment: macOS,
Node v25, Google Chrome (headless), Python http.server for static hosting.

## Automated checks (run this session)

```bash
cd ~/Desktop/stride
for f in web/api.js web/fixtures.js web/speech.js web/camera.js web/app.js; do node --check "$f"; done
node tests/browser/logic.test.mjs
```

Result: all modules parse; `logic.test.mjs` → **12/12 checks passed, exit 0**.

| ID | Check | Result |
| --- | --- | --- |
| U01 | route start → guiding @ index 0, emits speech event | pass |
| U02 | confirm advances; repeat does not advance | pass |
| U03 | final confirm completes once (3-step), no overflow | pass |
| U04 | pause/resume toggles; stop resets to idle | pass |
| U05 | vision paused until start, live after start | pass |
| U06 | camera selection increments source_revision, clears results | pass |
| U07 | live `/vision/latest` box is canonical xyxy, min<max, 0..1 | pass |
| U08 | speech dedupe by event_id (second offer rejected) | pass |
| U09 | expired event not queued, id recorded to block replay | pass |
| U10 | priority order urgent>fault>route>observation | pass |
| U11 | stale live observation (age>1000ms) unspeakable | pass |
| U12 | resetForSource clears consumed ids | pass |

## Static + boot checks

```bash
cd web && python3 -m http.server 8099   # 200 for index.html + all 5 modules
# headless Chrome --dump-dom: role label and data-role set by JS, no script errors
```

Result: all assets HTTP 200; ES module graph boots in headless Chrome with no
SyntaxError/ReferenceError/module-load failure. The viewer role label and
`body[data-role="viewer"]` are set by JS, proving the full import chain executes.

## Manual browser matrix (to run on real devices)

Not yet executed — requires a webcam, iPhone 14 and AirPods. Documented so it is
not silently skipped:

- [ ] Camera permission denied → clear message, no crash, stays viewer-safe.
- [ ] No camera present → stage shows empty state, no getUserMedia loop.
- [ ] Front/rear orientation; captured pixels unmirrored; preview mirroring does
      not reverse cue semantics.
- [ ] Session/source switch with late responses → old-source frames/results
      ignored (source_revision guard).
- [ ] Start once → continuous capture/announce without repeated Analyze.
- [ ] Duplicate poll / repeated event IDs → spoken once.
- [ ] Expired queued speech → dropped, not flushed on recovery.
- [ ] Urgent interrupt cancels current lower-priority utterance.
- [ ] Offline/stale (>1s no results) → live vision unavailable, overlays cleared.
- [ ] Manual checkpoint confirm; Repeat; Pause/Stop always reachable.
- [ ] Keyboard focus order, visible focus, VoiceOver labels, contrast.
- [ ] Real iPhone/AirPods playback; record browser/device versions.
- [ ] Two-client: viewer never calls getUserMedia; viewer hide stops only its
      own polling; explicit Stop is global.

## Known limitations / honest gaps

- Fixtures are labeled and explicit; they never substitute for a failed real
  call. A real-mode error is shown to the user, not hidden.
- Distance/haptics are simulated; UI animation is never a real vibration.
- No claim of a clear path from missing detections.
- Live phone→hosted YOLO→phone and W11 transport are unverified here; they are
  integration gates with Agents 1 and 3.
