# Phase 4 integration and next phone/audio slice

Source: Agent 1 software branch 4afb506, merged with vision main cbb9004.

## Delivered

Phase 4 was uploaded under `backend_phase3 2/`. Its changes are consolidated into
existing `backend_phase3/`, the README launch target. The duplicate directory is
removed. Phase 1/2 remain historical snapshots; do not run competing apps.
A further rename to `backend/` remains a coordinated Agent 1 task; no new runtime
was created for that rename. Agent 1 should pull main before continuing work.

Preserved vision dependencies and STRIDE_RECORD_STABLE_SIGHTINGS. Restored the
optional start_memory/close_memory lifespan hook omitted in the Phase 4 upload.
The existing real-model memory test failed against the unmodified Phase 4 app
(sightings stayed empty) and passes against this combined app.

DevKit firmware now uses implemented X-Device-Token authentication, strict
telemetry JSON, controller pairing, boot_id/kind/state_revision command fields
and received/executed/rejected/expired ACKs. It ACKs received before passing a cue
to the local loop; TTL subtracts poll + ACK + queue time. cancel stops remote cues
only. Local sensing and warnings never wait for networking. New shared parser
can be compiled on the host against actual API-generated command JSON.
See firmware/README.md and backend_phase3/DEVICE_INTEGRATION.md for exact contracts.

## Evidence

- Combined backend: 262 tests passed, real YOLO integration fixture enabled.
- Vision/integration: 38 tests passed, including stable memory + restart.
- Portable controller checks passed.
- Shared firmware parser: actual API command decoded; wrong device/session/boot,
  invalid TTL/revision, obsolete status and unknown kind rejected; stop/cancel
  recognized. This is host validation, not an ESP32 network exchange.
- Hardware-free real-app scenario passed: checked synthetic route -> 20 cm
  simulated obstacle -> blocked/old guidance invalid/stop command -> timeout
  remains blocked/unknown -> invalid no echo remains blocked -> three clear
  samples -> paused -> explicit resume -> guiding. Synthetic ACK recorded as
  reported execution, not physical movement. See qa/phase4-obstacle-cycle.json.
- Firmware build results are recorded in qa/phase4-firmware-compile.txt after
  completion. Camera build is syntax-only with the unconfigured-board gate.

Reproduce the hardware-free scenario (temporary DB, synthetic route only):

```sh
PYTHONPATH=.:backend_phase3 /tmp/stride-phase2-venv/bin/python scripts/simulate_obstacle_cycle.py
```

Reproduce actual API JSON -> shared firmware parser on this machine:

```sh
PYTHONPATH=.:backend_phase3 /tmp/stride-phase2-venv/bin/python scripts/simulate_obstacle_cycle.py --output /tmp/stride-obstacle-cycle.json
clang++ -std=c++17 -Wall -Wextra -Werror -I /Users/adhyannsingal/Documents/Arduino/libraries/ArduinoJson/src tests/vision/phase4_protocol_test.cpp -o /tmp/stride-phase4-protocol-test
/tmp/stride-phase4-protocol-test < /tmp/stride-obstacle-cycle.json
```

## Chair ahead versus move right

YOLO can identify a supported class such as chair and image left/center/right.
Tracker stabilizes observations. The adapter still emits speech_event=null:
Phase 4 does not implement final object/route/fault speech arbitration. Do not
turn every box or a haptic command into a final voice instruction.

A checked route can instruct a right turn at a manually confirmed checkpoint.
That is different from selecting a safe avoidance sidestep. One forward distance
sensor and object boxes do not establish walkable right-hand space, ground
conditions or the absence of an undetected hazard. No module currently proves
"chair ahead; move right" is safe, and this integration does not invent one.

## Immediate Agent 1 / Agent 2 interface work

Agent 1: preserve this integrated app; deploy one HTTPS instance with the model,
matching manifest, persistent SQLite storage and provisioned credentials. Complete
camera producer selection/freshness policy and the final speech-event arbiter.
For voice: prioritize urgent sensor holds and sensing faults over route cues,
then low-priority stabilized observations; invalidate old events on block/source
change/stop and expose stable event ID, priority, expiry and current revision.
This module is not yet supplied by Phase 4. Device status is audit/state data,
not a final speech queue; a delivered haptic command is one-shot for the device.

Agent 2: connect session auth, routes, route actions and memory to real responses.
Poll `/device/status` with authorized UI credentials; show fresh/unknown/source
and controller pairing truthfully. Connect final events to speech; cancel current
and queued routine speech on urgent holds. Review handoff/frontend-speech-fixes.patch.
Normalize route instruction/created_at/expires_at to frontend speech fields only
when valid and current. Test actual iPhone/AirPods phrase and interruption now,
without hardware. A simulation test must remain visibly labeled. AirPods pair to
the iPhone; the browser uses system SpeechSynthesis, not a configured cloud voice.
Frontend branch remains separate per its do-not-merge handoff; no UI was overwritten.

Agent 3: maintain vision/firmware regression evidence, review detection accuracy,
then immediately start sensor-only calibration on hardware arrival. Validate
rails/divided ECHO first, followed by local alerts and offline behavior, then
ESP32 HTTPS exchange and measured latency. W11 uploader remains blocked by exact
board verification AND camera API mismatch (camera-state missing, raw JPEG versus
multipart); its syntax compile is not end-to-end operation.

No hardware, hosted runtime, actual AirPods speech or independent walking safety
has been verified by these software checks. The next deliverable is a supervised
software/phone demonstration of instruction -> interrupting obstacle warning ->
unknown sensing warning -> explicit route resume. Automatic avoidance is not proven.
