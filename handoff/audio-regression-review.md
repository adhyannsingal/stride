# Speech review for Agent 2 — tested proposal, not applied UI

Source: feature/frontend 0f9500d, frontend/src/lib/speech.ts. Its handoff explicitly
says do not merge to main. Original and patched copies were tested under /tmp;
no frontend files/branch/design were overwritten. No external message was sent.

Four actual reproduced failures in five focused tests:

1. age_ms was frozen while an observation waited behind speech; a stale observation
   could be spoken after the 1000 ms cutoff if expires_ms was absent.
2. Unknown observation age was accepted rather than failing closed.
3. A cancelled utterance's delayed callback could clear the urgent utterance state
   and start lower-priority speech while urgent output was still active.
4. Previously queued routine output survived urgent preemption and could replay.
5. Existing event-ID deduplication already passed.

The patch accumulates queue residence with monotonic time, rejects unknown/invalid
observation age, invalidates callbacks with an utterance generation and discards
queued lower-priority events when fault/urgent arrives. No change to visuals,
public constructor call sites or backend endpoint names. Optional monotonicNow
on the clock interface allows deterministic tests; browser defaults to performance.now.

Original: 1 passed / 4 failed. Patched temporary copy: 5 passed / 0 failed.
Logs: qa/audio/speech-before-fix.txt, qa/audio/speech-after-fix.txt.
These tests mock speechSynthesis. They prove logic only, not audibility, iOS
callback behavior, routing, latency or AirPods connection.

Agent 2 can review/apply in its checkout after ensuring the target file still
matches; do not overwrite newer work:

```sh
git apply --check handoff/frontend-speech-fixes.patch
git apply handoff/frontend-speech-fixes.patch
node --test tests/integration/speech-regression.test.mjs
# Then rerun existing controller tests, tsc --noEmit and production build.
```

To reproduce without changing the frontend branch, export its source to a
scratch directory, apply the patch there and set STRIDE_SPEECH_MODULE to the
patched speech.ts path when running the same Node tests. Node 25.3.0 was used.
Actual frontend import/build and real iPhone/AirPods verification remain pending
until Agent 2 applies and reviews the change. Backend priority/verified capture
age are still required; a scheduler patch alone does not supply those policies.
