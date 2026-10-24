# Webcam tuning and fault-test follow-up

Branch: stride/hardware-vision. Based on Agent 3's existing model/service.
No physical hardware work was performed; parts are expected later per the human.
Model SHA256: `cbbde35333c4e002b9df32c16be0a7d43166fde7b86fd282a82dc7baaedb15c5`. CPU runtime on the local MacBook Air M4.

## Work completed in requested order

1. 60 s initial real camera run with per-stage profiling.
2. Candidate decoding optimization, aspect-ratio correction and CPU thread comparison.
3. 60 s tuned real camera run with recognition candidates.
4. Overload, expiry, capture-loss, logical source switch, pause/resume, stop/resume
   and repeated source replacement using actual camera JPEGs + actual YOLO runtime.

## Local live results

| Run | Result rate | Capture/result p50 | p95 | Max | Interpretation |
| --- | --- | --- | --- | --- | --- |
| Initial | 6.00/s | 46 ms | 76 ms | 283 ms | Nearly black input; transport/runtime timing only, no scene-recognition pass |
| Tuned | 5.61/s | 52 ms | 96.2 ms | 586 ms | Visible scene and actual detection candidates; performance gate PASS |

Initial input inspection was nearly black (mean pixel 0.0000029/255). The temporary
inspection image was deleted. Later visible input produced candidates including
cup, bottle, person, laptop, chair and book. These are model outputs, not verified
accuracy labels. Some predictions may be incorrect; no confidence threshold or
class-coverage claims were tuned without ground truth. Raw webcam images were
not retained. The final run had 3 nearly black frames
out of approximately 338 capture attempts.

Candidate class selection now runs in NumPy for all 2100 anchors before decoding
eligible boxes, preserving finite-value/score/geometry/NMS rules. Postprocess p95
was 2.26 ms initially and
0.99 ms in the tuned run. These were
DIFFERENT scenes/load, not a controlled before/after speedup or accuracy comparison.
Original/exported fixture parity still passes with nonempty supported detections.

A same-frame comparison of one/two/four ONNX CPU threads kept two threads: detector
p95 11.49/7.92/9.28 ms in that short comparison. Its input was still dark, so it is
latency evidence only. Production defaults remain two threads and score .35.
The tuned capture was 640x360, preserving the native 16:9 image instead of forcing
it into 640x480. Portrait/landscape geometry and dark-frame diagnostics are tested.
No change to the model artifact, input tensor shape or canonical XYXY API.

## Fault results: all seven cases PASS

- Overload: actual webcam capture with 200 ms injected inference delay, 141
  offers, 27 published results, 114 obsolete drops. Exactly
  one pending frame and one model job. p95 result age 322.3 ms;
  latest offered frame eventually processed.
- 1150 ms inference delay: completion discarded, zero published observations,
  unavailable state and no current objects.
- Capture stopped for 1.1 s: previous detections cleared at read time; stale state;
  prior observation failed is_current. No final speech is emitted by this service.
- Source switch, pause and stop during an in-flight job: retired frame never
  published; a fresh frame resumed successfully with new track IDs.
- Thirty source replacements during one held inference: one worker/model job;
  only the final revision published. This is a LOGICAL revision/producer switch
  on the same physical webcam, not a test between W11 and a second real camera.

The new rapid-switch regression first FAILED with 51 accumulated workers under
50 source changes (`source-switch-before-fix.txt`). Fix: retain the session worker
across rebinds; after an old job finishes, it reads the current session's newest
pending frame. No unsafe cancellation/restart of an active native inference is
used. Regression now passes and also verifies the final frame is processed.

## Reproduce

```sh
PYTHONPATH=. .venv/bin/python scripts/measure_live.py --seconds 60 --threads 2 --output qa/webcam-tuning-final.json
PYTHONPATH=. .venv/bin/python scripts/tune_live.py --output qa/webcam-thread-tuning.json
PYTHONPATH=. .venv/bin/python scripts/measure_faults.py --output qa/webcam-fault-results.json
.venv/bin/python -m pytest tests/vision tests/integration -q
```

22 Python tests PASS (one upstream TestClient deprecation warning). Fault harness
adds seven measured local camera/model scenarios. Test wrappers/threads/delays are
explicit diagnostic adapters, not alternate frontend or backend applications.

Hosted networking, final backend priority/speech on iPhone/AirPods, physical
camera-to-camera switching, W11 and sensor/motor behavior remain NOT RUN here.
Controlled moved/new/removed-object ground truth and false-positive/miss review
are still needed to complete scene-coverage acceptance. No laptop-free claim is
made from this local development run. See JSON reports for raw aggregate metrics.
