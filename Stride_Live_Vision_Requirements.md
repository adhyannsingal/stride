# Stride live vision requirement — highest priority update

**User correction:** the glasses must continuously monitor the view ahead while the wearer walks. A button-triggered photograph is not the core vision feature. This update overrides contrary perception/priority instructions in earlier handoff files. No continuous mode is implemented merely by writing this requirement.

## Locked six-hour architecture

```text
Glasses W11 camera → continuous fresh JPEG uploads over Wi-Fi
                                      ↓
                       Hosted lightweight YOLO detector
                                      ↓
                  fresh detections + boxes + stable object IDs
                                      ↓
                   iPhone web app → concise AirPods announcements

HC-SR04 → independent ESP32 loop → immediate local buzzer/vibration
Checked route → instructions and directional vibration
Gemini → optional requested description / unusual-object query
```

YOLO runs on a deployed server for this sprint, not on a laptop carried by the wearer. OpenCV can handle frame preprocessing/drawing/tracking; it is not the detection model. Keep the existing phone-web/FastAPI design. A native iPhone Core ML detector is a later optimization if signing/build access and time permit; do not start a second native app in this sprint.

## What live means

- Tap **Start navigation** once, with camera/upload consent; then capture and detect automatically until Pause/Stop. Do not require Analyze for each scene.
- Start at 640×480 capture and **target 5 fresh detector results/s**, reducing capture size/model input if measured performance requires it. This is a target to prove on actual hosting, Wi-Fi and W11, not a promised frame rate.
- Camera/transport rate, model inference rate and result age are distinct metrics. A smooth preview alone does not demonstrate live recognition.
- Initial engineering target: capture-to-result p95 ≤500 ms over a 60-second run. Results older than 1000 ms cannot be announced as current. These are provisional demo gates, not validated safe walking thresholds.
- Use a latest-frame slot per session; one detector job at a time for that session, discard obsolete pending frames. Never grow an inference backlog.
- Show actual result rate, capture age, source, dropped frames and connection status. A source switch clears old results.
- On stale/no results for >1 s, declare **live vision unavailable**, cancel/defer visual guidance and announce a deduplicated interruption. Never substitute a fixture or cached detection as a live scene.
- Stop/pause/page-hide cancels capture/output; resuming requires an explicit action. Keep phone foreground for the current web implementation.

Do not narrate every object on every frame. Match stable detections across frames with lightweight class/box association or an existing tracker; require two consistent observations for ordinary announcements. Announce new/meaningfully changed objects with a 3 s cooldown per track/position. The sensor alert always preempts speech and route vibration. Ordinary object detections do not automatically command evasive turns.

## Detector and deployment

Agent 3 selects one small pretrained YOLO detector and pins checkpoint/runtime/input size/class list. Prove it locally on live webcam images immediately. For cloud deployment, prefer an exported ONNX model with ONNX Runtime CPU if it meets the measured throughput/memory gate; keep heavyweight conversion/training packages off the serving path. Use the model's exact preprocessing, output decoder and NMS behavior, not a guessed tensor layout. Compare exported and original outputs on a few test images before deployment.

The deployed process must fit the chosen host's actual memory/CPU allocation. Model download/load, sustained rate and thermal/network behavior are tested, not inferred from model marketing. No new paid resource without team authorization. If hosted performance fails the live gate, record the failure and reduce input/model overhead within a short timebox. A snapshot-only fallback can be demonstrated as such, but **does not satisfy this core requirement**.

The first 45 minutes of implementation must prove a live detector path; by minute 90 prove phone-to-hosted-detector-to-phone behavior. W11 transport remains a final-integration gate, not something validated by a laptop webcam test. Preserve enough time to test with the glasses actually mounted and moving under supervision.

## API extension

Keep existing endpoints for routes, memory, devices and optional Gemini questions. Add:

- `POST /vision` — `action_id`, `session_id`, `action=start|pause|resume|stop`; authorize the selected camera/session and return live state. Also controls the phone capture loop. W11 honors the selected session/source and stops or pauses uploads based on status/config.
- `GET /vision/latest?session_id=...` — `state_seq`, `frame_id`, `captured_ms`, `completed_ms`, `age_ms`, `result_hz`, `source_revision`, `origin`, `source`, `status=live|stale|paused|unavailable`, object records and deduplicated speech event. Include stable track IDs, model scores and labels; scores are detector scores, not calibrated safety probabilities.
- Existing raw `POST /frame` uploads feed the detector automatically while live mode is active. Do not call Gemini on every upload.
- Extend `/status` with `vision` state/age/rate; frontend can poll `/vision/latest` every 200 ms while active, back off and abort on hide/stop. Never replay an old event ID from repeated polls.

Live detector observations may feed sightings with capture timestamp and last-confirmed checkpoint association. The existing 5-second freshness policy applies only to requested Gemini snapshots; the stricter live policy above controls automatic visual announcements. Distinguish provider `yolo` from `gemini` and fixtures.

## Current three-person ownership

1. **Agent 1 — backend:** FastAPI/shared contracts/auth, frame ingestion, routes/memory, all device server policies/commands/ACKs, app assembly and HTTPS deployment.
2. **Agent 2 — frontend:** browser/webcam capture and upload, accessible phone UI, overlays, route controls and AirPods speech playback. Software only.
3. **Agent 3 — Adhyann:** model/runtime/export, latest-frame inference/tracking/router, W11 and DevKit firmware, simulation client, physical hardware and measured integration. No duplicate frontend/backend.

Read `Agent_1_Backend.md`, `Agent_2_Frontend.md`, `Agent_3_Hardware_Vision.md` and `contracts/API.md`. Agent 1 is the sole writer of shared schemas/settings/dependencies/app entrypoint. Agent 3 supplies the mounted vision service; Agent 2 consumes the shared API. The integration gates and merge order live in Agent 3's brief. Use actual remaining time; reserve the final build hour for staged hardware integration and the separate submission hour for recording.

## Required extra tests

- **L01:** 60-second live feed, moving/new/removed supported objects, no repeated Analyze clicks; log frame/result rate and p50/p95/max capture age.
- **L02:** introduce slow inference/network loss; no backlog grows, stale result never becomes speech/turn guidance; live-unavailable state appears.
- **L03:** switch camera/pause/resume; old-source frames/results/tracks cannot replay.
- **L04:** verify stabilized announcements and cooldown; local stop alert interrupts current speech and queued turn.
- **L05:** final glasses-mounted W11 feed → hosted detector → actual iPhone/AirPods path; record raw capture rate separately from detector rate. A phone-camera fallback must be disclosed and does not prove W11 operation.
- **L06:** scene coverage check includes supported classes and missing hazards; record misses instead of claiming universal detection.

“Everything ahead” is the product aspiration, not a guarantee. A common pretrained detector recognizes a fixed label set; glass, stairs, holes, walls and other hazards may be absent or missed. Bounding boxes are not measured depth or safe-path geometry. Use a controlled route and sighted spotter; this build is not validated for independent blind walking or road crossings.

## References

- [YOLO streaming inference and stale-frame buffering](https://docs.ultralytics.com/modes/predict)
- [ONNX export/runtime path](https://docs.ultralytics.com/integrations/onnx/)
- [COCO class coverage](https://docs.ultralytics.com/datasets/detect/coco/)
- [Apple live object recognition](https://developer.apple.com/documentation/vision/recognizing-objects-in-live-capture)
- [Core ML deployment as a future phone path](https://docs.ultralytics.com/integrations/coreml)
