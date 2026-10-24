# Stride — current team build spec

Navigation assistance glasses combining checked-route guidance and Route Memory, immediate local obstacle alerts, continuous objects-ahead awareness, AirPods speech and directional vibration. Object finding/last-seen recall is supporting functionality. This is an implementation pack, not evidence of completed software or hardware.

## Give each coding agent exactly one brief

| Agent | Workstream | Start file |
| --- | --- | --- |
| 1 | Backend, shared contracts, all device server code, deployment and application assembly | [Agent_1_Backend.md](Agent_1_Backend.md) |
| 2 | Frontend, browser capture, route controls, accessibility and speech playback | [Agent_2_Frontend.md](Agent_2_Frontend.md) |
| 3 — Adhyann | Live vision model/service, firmware, hardware and measured integration | [Agent_3_Hardware_Vision.md](Agent_3_Hardware_Vision.md) |

These assignments replace every older agent-number allocation. Agent 1 owns shared files; other agents request exact compatible changes. Agent 3's integration section defines branches, seams, merge order, time gates and final tests. Implement working vertical slices in parallel; do not wait for hardware or another planning phase.

## Runtime and core acceptance

W11 continuous JPEG → hosted FastAPI → lightweight YOLO → iPhone web app → AirPods. HC-SR04 → independent DevKit → local buzzer/protected 3 V motor. Checked route → backend-issued expiring cue → DevKit. MacBook is development only. Gemini descriptions are optional; OpenCV is supporting image code, not the detector.

Start once, then continuous detection without repeated Analyze clicks. Target 5 fresh results/s and capture-to-result p95 ≤500 ms over 60 s; record actuals. No live announcement from a frame older than 1000 ms. Drop pending obsolete frames, invalidate source changes and suppress stale output. Local sensor alerts continue without the network. Route checkpoints require explicit confirmation; detections do not establish a safe path or measured depth.

[Shared API contract](contracts/API.md) · [Live vision requirements](Stride_Live_Vision_Requirements.md) · [Full wiring guide](Stride_Hardware_Wiring_Guide.md).

Confirmed kit: W11 ESP32-S3/OV3660 (exact pinout still requires vendor/PCB confirmation), separate ESP32 DevKit V1, HC-SR04 with 5 V ECHO divider, switched buzzer, protected regulated 3 V motor, pocket USB bank, iPhone 14 and AirPods Pro 3. Standard iPhone 14 has no LiDAR. Normal speech is included; world-anchored audio is unproven stretch.

Original budget: six hours build plus one hour recording/submission; subtract elapsed time. Integrate every 45 minutes, reserve the final build hour for staged hardware work, cut Gemini/GPS/voice input/second motor before continuous perception. Demonstrate on a checked controlled route with a sighted spotter. Never present a webcam/simulator test as validated glasses operation.

Reviewed repository main `905b2218a142be9b20696ba823db63444e9b5f91` and software `5cc61fde5f1b65764d5dc8f47aab28be52122aa1`: docs only, no executable app/tests to validate. Agents must fetch/recheck for new code before implementing. Use configured Git attribution, preserve teammates' work and never commit secrets or force-push.
