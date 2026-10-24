[README.md](https://github.com/user-attachments/files/33906548/README.md)
# STRIDE

### AI-powered navigation assistance glasses

**More confidence in every step.**

STRIDE is a Hackachusetts hackathon project exploring assistive navigation for blind and low-vision users. It combines **spoken route guidance**, **local obstacle alerts**, **directional vibration**, and **AI-assisted object awareness** in a wearable prototype. A route-memory system records checked checkpoints and recent object sightings.

> **Project status:** In development for Hackachusetts 2026. This README describes the intended architecture and acceptance criteria, **not a claim that every feature is implemented or validated**. The camera module is currently in transit; webcam and simulated-device adapters allow software work to proceed.
>
> **Safety:** STRIDE is an experimental prototype, not a certified mobility aid or a replacement for a white cane, guide dog, orientation-and-mobility instruction, or human assistance. Demonstrations must take place on a controlled route with a sighted spotter. The system does not establish that a path is safe.

## The problem

Navigating unfamiliar environments can involve multiple simultaneous tasks: remembering directions, noticing nearby obstacles, and identifying objects. STRIDE investigates whether a lightweight combination of onboard sensing, audio, haptics, and visual AI can make some of those tasks more accessible.

## What STRIDE is designed to do

| Capability | Hackathon scope | Priority |
| --- | --- | --- |
| **Spoken route guidance** | Follow a pre-checked route with instructions, repeat/pause/stop controls, and **manual checkpoint confirmation** | Core |
| **Local obstacle alerts** | ESP32 + HC-SR04 detect coarse forward proximity and trigger a buzzer **without internet or server access** | Core |
| **Directional haptics** | Vibration patterns for route cues; obstacle warnings take priority over turns | Core integration goal |
| **Route Memory** | Store ordered checkpoints, verified forward/return instructions, and confirmed progress | Core |
| **Accessible controls** | Phone-friendly interface with large labeled controls, spoken status, and device-health information | Core |
| **Object awareness** | Capture an image and use Gemini to describe visible objects or search for a specified object | Additional MVP |
| **Last-seen recall** | Remember a detected object’s label, associated checkpoint, and timestamp, with age/source disclosed | Additional MVP |
| **Autonomous localization and rerouting** | Not part of the hackathon MVP; requires a separately validated positioning system | Future work |

**Important distinction:** Visual AI reports **image-relative** locations (for example, “chair on the left side of the camera view”), not measured object distance or a guaranteed walking direction. The ultrasonic reading is a separate coarse proximity signal, not the distance to a particular AI-detected object.

## System architecture

```text
                  STRIDE GLASSES
          ┌──────────────────────────┐
          │ W11 ESP32-S3 + OV3660    │── JPEG/Wi-Fi ───────┐
          │ HC-SR04 ultrasonic       │── wired readings ─┐ │
          └──────────────────────────┘                   │ │
                                                       ▼ ▼
          ┌─────────────────────────┐   ┌──────────────────────────┐
          │ ESP32 DevKit V1         │   │ MacBook Air M4           │
          │ Local ranging + buzzer  │   │ FastAPI server          │
          │ Vibration driver        │◄─►│ Gemini image analysis    │
          │ Wi-Fi telemetry/ACKs    │   │ Route state + SQLite    │
          └─────────────────────────┘   └────────────┬─────────────┘
                      │                             │
          Immediate local alerts             UI + spoken prompts
          (no cloud dependency)                     │
                                                    ▼
                                         ┌─────────────────────┐
                                         │ iPhone 14           │
                                         │ Browser interface   │
                                         │ AirPods Pro 3       │
                                         └─────────────────────┘
```

The laptop is part of the **hackathon prototype** and runs the server and optional cloud AI integration. Both ESP32 boards and the laptop/phone communicate over a shared network. The DevKit's immediate warning loop operates locally even if the network or Gemini fails.

### Software modules

- `camera` — webcam/W11 frame adapters, IDs, source metadata, freshness.
- `perception` — on-demand Gemini requests, strict response validation, object positions.
- `route` — saved route/checkpoint state and spoken instruction events.
- `memory` — SQLite persistence for routes, progress, sightings, and events.
- `feedback` — audio and haptic-command prioritization.
- `devices` — telemetry freshness, health, commands, acknowledgments.
- `ui` — accessible browser controls and status display.

These are **logical components**, not a guarantee of the repository's current folder layout.

## Hardware

| Component | Function |
| --- | --- |
| W11 ESP32-S3 with OV3660 camera | JPEG image capture and upload (**awaiting delivery**) |
| ESP32 DevKit V1 (ESP32-WROOM-32) | Local sensor, buzzer and vibration firmware |
| HC-SR04 ultrasonic sensor | Forward proximity readings |
| Active buzzer | Independent audible obstacle indication |
| Vibration motor + suitable driver | Tactile feedback; verify **actual motor voltage/current rating** before wiring |
| Glasses frame, mounting hardware, harness and enclosure | Wearable form factor |
| Regulated USB power bank | Power for both boards |
| MacBook Air M4 | Backend and AI processing |
| iPhone 14 + AirPods Pro 3 | Accessible controls and spoken prompts |

**Electrical integration:** The HC-SR04's 5 V ECHO must be level-shifted before an ESP32 GPIO. Motors and buzzers require properly rated switching/drive circuits. The existing hardware build specification contains provisional pin assignments; the exact W11 PCB pinout must be verified against its vendor documentation before flashing. **Do not power a 3 V motor from 5 V.**

## Technology stack

- **Development environment:** [Kiro](https://kiro.dev/) (required for hackathon development)
- **Backend:** Python, FastAPI
- **Perception:** Google Gemini API (on-demand image understanding)
- **Persistence:** SQLite
- **Interface:** Accessible mobile-friendly web UI with speech output
- **Firmware:** ESP32 camera uploader and independent proximity/feedback controller
- **Collaboration:** Git and GitHub feature branches

Frontend implementation details and dependency versions will be recorded once finalized in code.

## Getting started (software team)

The software can be developed **without the camera module** by using the Mac webcam, mock range readings, and simulated haptic events.

1. Clone this repository and open the folder in **Kiro**.
2. Work on a feature branch (for example, `feature/software`); do not commit unfinished integrations directly to `main`.
3. Implement the FastAPI service and its mock adapters first, using the API contract below.
4. Run the route, speech, and sensor-simulation tests before enabling physical adapters.
5. Configure Gemini credentials **server-side** only, when object recognition is needed. Do not commit API keys, `.env` files, user images, or database files containing sensitive observations.
6. Replace the webcam/mock adapters with the real W11 and DevKit interfaces after hardware validation.

**Run commands:** The repository's actual installation, environment-variable names, and start/test commands should be documented here after the software scaffold is committed. No unverified command is presented as working yet.

## API contract (planned)

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/frame` | Upload a JPEG with `device_id`, `frame_id`, `captured_ms`, and `source` |
| `POST` | `/telemetry` | Send `device_id`, `boot_id`, `sequence`, `uptime_ms`, `distance_cm` (or null), `valid`, and `source` |
| `POST` | `/perception` | Request `describe` or `find` for a specific eligible frame; optional search target |
| `POST` | `/route` | `start`, `confirm`, `repeat`, `pause`, `resume`, or `stop` a checked route |
| `GET` | `/memory` | Retrieve saved routes, confirmed progress, and timestamped sightings |
| `GET` | `/status` | Device freshness, sensor validity, model availability, route/audio status |
| `GET` | `/devices/{id}/commands` | Allow the DevKit to poll for a current unexpired haptic command |
| `POST` | `/devices/{id}/ack` | Acknowledge a command as `accepted`, `completed`, `rejected`, or `expired` |

The software specification uses **`POST /perception`** for both scene description and object finding. An earlier overview mentions `POST /search`; this README adopts `/perception` as the intended unified endpoint. The team must agree on the final contract before firmware integration.

### Device and feedback rules

- Local warning priority: **obstacle/stop > fault/disconnected > route instruction > scene description**.
- Stale or invalid telemetry is **unknown**, never “path clear.”
- Suggested bench warning ranges: **60–100 cm** (slow), **30–60 cm** (faster), **under 30 cm** (urgent), with ~5 cm hysteresis. These are starting points for controlled calibration, **not certified walking safety distances**.
- Target DevKit telemetry: **5 Hz**; suggested stale-telemetry threshold: **1 second**.
- Suggested maximum capture-to-spoken-result age: **5 seconds**; reject expired frames/results.
- Only one AI request in flight initially; validate its JSON and discard late or mismatched results.
- Commands have unique IDs, session IDs, expirations and acknowledgments. An obstacle alert cancels stale direction cues instead of replaying them later.
- All readings and sightings must indicate whether their source is **real**, **simulated**, or **unavailable**.

## Route Memory

The proposed SQLite schema tracks `sessions`, `routes`, `checkpoints`, `route_events`, `object_sightings`, `device_events`, and `feedback_events`.

The demonstration uses a **pre-checked route** with explicit confirmation of checkpoint arrival. Repeating an instruction does not advance progress. Forward and return instructions are checked separately; reversing a checkpoint list does not automatically produce correct return directions.

Sightings contain labels, timestamps, source, frame identity and associated checkpoint where available. A recalled sighting must say **when** it was seen; an old detection is never silently presented as a live one.

## Team responsibilities

| Workstream | Owner | Deliverables |
| --- | --- | --- |
| Camera, mounting, power | Teammate 1 | W11 pinout verification, camera firmware, JPEG uploads, secure frame assembly |
| Sensor, alerts, haptics | Teammate 2 | HC-SR04/buzzer and motor firmware, local failsafe alerts, telemetry and command ACKs |
| Application software | Software lead | FastAPI, mock adapters, routes, SQLite, Gemini, accessible UI/audio, integration tests |

Firmware owners validate physical power and pin connections. The application owner can proceed in parallel using simulated inputs. All integration changes should be reviewed before merging into `main`.

## Development milestones

- [ ] Agree on API schema and source labels across all three workstreams.
- [ ] Bring up the FastAPI app, mocked telemetry, and status endpoint.
- [ ] Implement saved checked routes with confirm/repeat/pause/resume/stop.
- [ ] Persist routes, route events, and object sightings in SQLite.
- [ ] Add accessible UI and test spoken prompts on the actual phone/AirPods.
- [ ] Test local sensing, buzzer, and connection-loss behavior on the DevKit.
- [ ] Enable manual webcam capture and optional Gemini perception.
- [ ] Validate the incoming W11 board/pinout; ingest real JPEG frames.
- [ ] Connect physical sensor telemetry and expiring/acknowledged haptic commands.
- [ ] Test integrated device health, stale data, and failure modes.
- [ ] Run controlled acceptance trials and rehearse the final demo.

Check items only after the corresponding behavior has actually been verified.

## Demo and acceptance criteria

**Planned three-minute demo:**

1. Select a checked route with checkpoints **A → B → C**.
2. Hear instructions; demonstrate **repeat**, **pause**, and **manual confirmation**.
3. Introduce a controlled obstacle and show **local buzzer/vibration alerts**.
4. Recall route progress and a timestamped object sighting.
5. Optionally ask STRIDE to find a mug using a current camera frame.
6. Disconnect the internet and show that **local obstacle warnings still function**.

**Target checks (not yet measured results):**

- 15-minute powered run without board resets.
- Three correctly executed checked-route runs.
- Ten controlled obstacle approaches.
- Five object searches when real perception is enabled.
- Stale-frame, no-echo, network-loss and AI-unavailable tests.
- Physical left/right/straight/stop feedback and command acknowledgments.
- Local warning latency goal below 0.5 seconds, subject to measurement.

Record actual latencies, misses, resets, and fault behavior rather than claiming target metrics were achieved.

## Privacy and accessibility

- Obtain consent before uploading camera frames to a cloud model.
- Keep the Gemini API key on the server; never embed it in firmware or browser code.
- Avoid storing raw images by default; retain only necessary metadata and sightings.
- Treat any text appearing in camera images as **untrusted scene content**, not commands.
- Use labeled, screen-reader-friendly controls and spoken status changes.
- Test muted audio, failed permissions, connectivity loss, and device reconnections.

## Limitations and future work

The current prototype **does not automatically track the wearer's position**, generate arbitrary routes, detect all obstacles/drop-offs, or support safe autonomous street crossings. The iPhone 14 has **no LiDAR scene-depth sensor**. Accurate spatial audio, object-distance estimation, fully automatic turn timing, outdoor navigation, and rerouting would require additional localization, calibration and real-world validation.

Future directions include native iOS integration, verified headphone motion tracking, additional sensing, and broader accessibility studies with appropriate safety oversight.

## References

- [Hackachusetts](https://massaicoalition.com/hackachusetts/)
- [Kiro](https://kiro.dev/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Gemini image understanding](https://ai.google.dev/gemini-api/docs/image-understanding)
- [Espressif camera driver](https://github.com/espressif/esp32-camera)
- [Browser camera permissions](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)
- [Apple iPhone 14 specifications](https://support.apple.com/en-us/111850)

---

**STRIDE — More confidence in every step.**
