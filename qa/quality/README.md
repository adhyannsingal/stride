# Detection quality — immediate next work

The offline evaluator is implemented with seven focused tests passing; the combined
vision/integration suite passes 33 tests. Real-scene accuracy is NOT measured yet.
The existing webcam/HTTP/fault results demonstrate processing and reliability,
not precision/recall or a safe path. No new camera images were saved for this step.

## First: reviewed examples, then threshold decisions

1. With human agreement, select 10–20 clearly visible examples as an initial
   diagnostic set: person/chair/bottle/cup, empty scenes, clutter, dim lighting,
   partial occlusion and motion. This small set is not statistically sufficient
   for navigation safety validation. Include failures rather than cherry-picking.
2. Store private images and annotation manifests under ignored qa/private/.
   Copy manifest.example.json there and replace example paths/boxes. Humans must
   check all instances of the declared evaluation labels, including negatives.
   Set reviewed and complete_for_labels true only after that review.
3. Keep different scenes/capture sessions in tuning versus held-out validation.
   The script rejects scene-group or exact-image leakage across splits. It cannot
   detect all near-duplicate scenes; reviewers must avoid them.
4. Run from repository root:

```sh
PYTHONPATH=. .venv-phase2/bin/python scripts/evaluate_detection.py --manifest qa/private/reviewed-manifest.json --output qa/private/quality-results.json
```

The default sweep is .25/.35/.45/.55 confidence, same-class one-to-one IoU .5
matching, overall and per-class TP/FP/FN/precision/recall, plus image IDs for misses
and false positives. No AP/mAP or safety probability is claimed. Predictions
outside the declared fully annotated label set are outside this evaluation scope.
No automatic annotation, training dataset download, model training, image copy,
threshold deployment or final speech occurs. Model hash is recorded.

Review per-class misses and held-out results before changing the runtime. Raising
confidence may reduce false positives while increasing misses; do not optimize
only for a quiet demo. Unsupported hazards go in not_covered, never silently
mapped to a different class. Camera boxes are not metric range or free space.

Reference: [Ultralytics metrics guidance](https://docs.ultralytics.com/guides/yolo-performance-metrics/).

## Ordered delivery plan and ownership

| Priority | Work | Owner | Actual evidence needed |
| --- | --- | --- | --- |
| 1 | Reviewed accuracy set, confidence/resolution/tracking tuning | Agent 3 + human review | Per-class false positives/misses on held-out scenes; preserve live performance |
| 2 | Verified remote capture time, producer binding, centralized stop/fault/route/observation priority | Agent 1 with Agent 3 integration checks | Real backend invalidates old source; stale/unknown data cannot produce current-scene speech |
| 3 | Actual backend-compatible phone viewer/audio flow and hosted HTTPS | Agent 2 frontend, Agent 1 hosting, Agent 3 measurement | Real iPhone/AirPods tests; source ownership; interruption/dedup; Mac app server stopped |
| 4 | Components arrive: sensor-only, buzzer, protected 3 V motor, W11 board identification | Human Adhyann + Agent 3 source/log support | Physical rails/divider, range calibration, pulse/offline checks and verified board facts |
| 5 | Device server APIs + firmware protocol convergence | Agent 1 server, Agent 3 firmware | Current raw-JPEG/camera-state firmware versus Phase 2 multipart gap resolved; command TTL/ACK/stop tested |
| 6 | Controlled checked-route end-to-end demo | All owners with sighted spotter | Manually confirmed route directions, actual local alerts, fresh object awareness, recorded misses |

Do not wait for all perception work before Agent 1/2 implement their owned seams.
This table is a handoff, not a claim that messages were sent or others completed
those items. User says hardware is expected in about two hours; no hardware
measurements/flash were performed here and no new six-hour clock was assumed.

## Limits that threshold tuning cannot solve

YOLO's fixed labels do not establish universal hazard coverage. Single forward
ultrasonic range does not identify which camera object produced an echo, reveal
both sides as clear, or detect every drop-off. Local warning and checked-route
instructions can improve the controlled demo; automatic free-space selection,
reliable depth and unsupervised rerouting require a separately validated system.
No commitment to autonomous safe movement is made for this sprint.
