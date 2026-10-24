# Next steps — run the live demo, then connect hardware

Reviewed main `cbb9004` and frontend `7b8e1ab`, then incorporated concurrent Phase 4 delivery `a70f338` without overwriting it. Updated 2026-10-24 after the user confirmed there is no deployed URL. The webcam measurement below was taken before that Phase 4 merge; see `handoff/phase4-integration.md` for its new device interfaces. This is the current implementation check, not the old docs-only review. Do not rebuild the working detector or make another frontend/backend.

## Already verified in this checkout

- Existing Phase 3 backend + real ONNX model + laptop webcam, actual loopback HTTP: 60.08 seconds, 652 unique results, **10.85 results/s**, capture-to-completion **p95 56 ms**, response-age p95 134.35 ms, zero HTTP errors. See `qa/current-webcam-http.json`.
- Camera/server shared the same OS clock through the trusted benchmark hook. These are local measurements, not hosted/W11/phone latency. Twelve nearly-black input frames were observed; output labels are model predictions, not human-verified accuracy.
- Backend tests before the concurrent Phase 4 merge: 184 passed, one opt-in real-fixture test skipped. After preserving Phase 4: **261 passed, one opt-in real-fixture test skipped**. Vision/integration tests: 36 passed, two optional-fixture tests skipped. One upstream TestClient deprecation warning. No physical hardware/audio result is implied.
- Existing `scripts/preview_live.py` launched successfully: 640×480, real local model. It remains a diagnostic; it does not upload, write Route Memory or speak. Q/Esc closes and releases webcam; P pauses. Do not open a second capture process at the same time.

## Immediate laptop demo

This checkout has the checksum-verified ignored model and existing development interpreter available. Relaunch from repository root:

```sh
PYTHONPATH=. /tmp/stride-phase2-venv/bin/python scripts/preview_live.py
```

That interpreter path is machine-specific. Other machines follow README environment/model setup. Move supported objects in view and observe new/removed boxes; missing detections never establish a clear path. This is the working local visual demonstration today, not an integrated spoken-navigation claim.

## Next software slice — exact owners

**Agent 1:** publish one supported public contract for the actual Phase 3 runtime. Coordinate with Agent 2 before changing it. Existing backend is multipart `/frame`, `/auth/session` with provisioned credentials, `/time.server_ms`, normalized `objects[].bbox`, and terminal vision stop. Routes/memory now exist but need session authorization. Phase 4 now supplies sensor transport, commands/ACK and obstacle route blocking, with matching DevKit protocol changes. Preserve those services; finish explicit capture-producer binding, trusted remote freshness and final obstacle/fault/route/observation speech arbitration. Do not emit unarbitrated object speech merely to make a demo talk. Serve the frontend build from the same origin; hosting is a later deployment of this same working app, not another app.

**Agent 2:** adapt the existing `frontend/src/lib/api.ts` once to the agreed actual backend. Current branch expects `/auth`, `/sessions`, raw JPEG, `box`, and route/memory shapes that differ. Do not merge an incompatible UI or silently fall back to fixtures. Existing Phase 3 route actions after start require `navigation_id` and `expected_revision`; route guidance uses `instruction`, `created_at`, `expires_at`, `event_id`, `state_revision`, `valid`. Normalize only after validity/expiry/revision checks. Preserve the branch's do-not-merge instruction until its owner releases it. Review the existing speech regression patch and test actual audible output separately.

**Agent 3 / Adhyann:** keep model/firmware tests passing; provide real live/fault measurements, supported-class/coverage checks and hardware bring-up. Don't build a second UI, inference queue or session/auth service. Existing model plugin runs inside Phase 3's worker. Close the diagnostic preview before another producer opens the webcam.

## Integration gates, in order

1. Real frontend login/session → backend health/results, with explicit errors rather than fixtures.
2. Mac is the only capture producer. Phone viewer joins the same session without requesting its camera or changing source. Opening/hiding viewer must not stop the Mac producer. For a first local test use the Mac UI; actual phone access requires a reachable frontend/backend origin. Camera-permission and secure-cookie configuration must match that origin; don't expose local-dev bypass as a hosted setup.
3. Route instruction and fresh stable object event reach the shared speech scheduler exactly once; expiry, pause/stop and urgent interruption pass. AirPods may pair to Mac for a first local audio-only check, or iPhone for the intended phone test. Pairing/audio output is human-controlled, not confirmed by UI text.
4. Deploy the same combined app on HTTPS, then repeat Mac-camera → hosted YOLO → phone/audio measurements. No deployment is currently available; no hosted or physical AirPods test is claimed.
5. When parts arrive, immediately begin **sensor-only → buzzer → protected regulated 3 V motor**, verifying rails/divider first. Confirm local warnings survive loss of Wi-Fi. In parallel identify the exact W11 PCB/pin map before camera flashing.
6. Verify the now-aligned Phase 4 DevKit protocol on actual boards: it uses X-Device-Token, controller pairing and its implemented command/ACK schema. See `backend_phase3/DEVICE_INTEGRATION.md` and `handoff/phase4-integration.md`; no actual ESP32 network exchange is yet claimed. W11 remains blocked by missing camera-state and raw-JPEG versus multipart mismatch as well as exact board facts. Agent 1 owns server adapters; Agent 3 owns firmware client changes.
7. Explicitly switch the session producer from Mac to verified W11, stop Mac capture, and test glasses → host → phone/AirPods. Prove local motor alerts offline and run the final supervised checked-route rehearsal. Stop the Mac backend to distinguish hosted operation from development fallback.

Use the actual remaining deadline. Prepare firmware now; don't wait until submission time for staged hardware checks. Keep Gemini/GPS/voice input/cosmetic work behind these gates. The new measurement report contains aggregate metadata only; no camera images, tokens or recordings were saved by this check.
