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

## Limits that threshold tuning cannot solve

YOLO's fixed labels do not establish universal hazard coverage. Single forward
ultrasonic range does not identify which camera object produced an echo, reveal
both sides as clear, or detect every drop-off. Local warning and checked-route
instructions can improve the controlled demo; automatic free-space selection,
reliable depth and unsupervised rerouting require a separately validated system.
No commitment to autonomous safe movement is made for this sprint.
