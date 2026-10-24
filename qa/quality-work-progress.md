# Current work evidence

- Root Phase_1 removed and pushed to main in 46c1976. backend_phase1 code and
  original authorship/history preserved. No history rewrite performed.
- 12 actual webcam JPEGs captured under ignored qa/private/initial-tuning-review/;
  one dark frame skipped. All images are tuning-only, reviewed=false and
  complete_for_labels=false. Accuracy NOT RUN until human labels and an independent
  validation scene are available. No private image/manifest committed.
- Private capture helper refuses output outside qa/private and nonempty folders;
  tests verify it cannot auto-label ground truth and releases the camera on errors.
- Existing Phase 2 capability probe confirms /routes, /route and /memory/export
  are absent; saved_routes_ready=false. No mocked backend response claimed real.
- Actual Agent 2 speech controller reviewed from feature/frontend 0f9500d:
  four regressions reproduced; tested proposal passes all five mocked-audio tests.
  Patch not applied to frontend branch and no AirPods playback was performed.
- Detailed ordered work/owner/acceptance plan: handoff/next-integration-plan.md.
  This is not a claim that backend/frontend owners completed or received messages.

Validation: 36 combined Python tests pass; proposed speech patch applies cleanly
to the reviewed original in a scratch checkout and all five Node regressions pass.
Node tests mock audio; actual phone/AirPods remains NOT RUN.
