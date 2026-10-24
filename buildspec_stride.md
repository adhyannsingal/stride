# STRIDE

**Updated October 24, 2026:** use `Stride_Hardware_Wiring_Guide.md` and `Stride_Software_Build_Spec.md` for the detailed implementation. Confirmed equipment: MacBook Air M4, iPhone 14, AirPods Pro 3 and a 3 V motor. The iPhone has no LiDAR; the motor requires regulated 3 V. See `Stride_Tonight_Plan.md` for webcam development without the boards/sensor.

## Project and scope

**Navigation assistance glasses for blind and low vision users.** Stride combines spoken route guidance, immediate obstacle alerts and Route Memory. Object finding and last-seen recall are additional features. The intended product supports indoor and outdoor journeys.

**Team:** 3 people · **Build window:** 36–48 hours · **Priority:** hardware first, navigation first.

The hackathon build demonstrates guidance along a checked route with explicit checkpoint confirmation. Automatic position tracking, arbitrary destination routing and rerouting require a localization system beyond the current hardware. This distinction limits the initial demo, not the project’s purpose.

## Features and priorities

| Priority | Feature | Implementation |
| --- | --- | --- |
| Core | Spoken route guidance | Select a saved route; speak the next instruction; support repeat, pause and checkpoint confirmation. |
| Core | Immediate obstacle alerts | DevKit reads HC-SR04 and controls buzzer locally, independently of cloud or Wi-Fi. |
| Core | Route Memory | Store ordered checkpoints, checked forward/return instructions and confirmed progress in SQLite. |
| Core | Accessible controls and status | Large labeled buttons, screen-reader labels, spoken state changes; dashboard shows connections, sensor validity and latency. |
| Additional MVP feature | Object finding | W11 image → Gemini detection → image-relative left/center/right spoken cue; report not found or unavailable. |
| Additional MVP feature | Last-seen recall | Save object, checkpoint and time; report the age of the sighting. |
| Stretch | Voice input, automatic localization, outdoor map routing, native ARKit/spatial audio and TimescaleDB; LiDAR is unavailable on the confirmed iPhone | Start only after the core demo passes and required devices are confirmed. |

## Architecture and placement

```text
GLASSES FRONT
  W11 ESP32-S3 + OV3660                 HC-SR04 facing forward
          | JPEG over Wi-Fi                     | wired harness
          v                                     v
  LAPTOP: FastAPI + Gemini + SQLite      COLLAR: ESP32 DevKit V1
          | route/search/status                 | local control
          v                                     v
  PHONE: controls + spoken guidance      COLLAR BUZZER / 3 V wrist motor

POCKET: dual-output USB power bank → separate USB cable to each ESP32 board
```

Mount the camera above one lens and the HC-SR04 beside it, level and unobstructed. Run sensor wires along the frame and down to the collar. Keep the DevKit and drivers in an insulated collar enclosure; keep the buzzer away from the ear. Secure cables with strain relief, slack and a quick disconnect. Check weight, heat and antenna clearance before wearing.

Both boards, laptop and phone share one Wi-Fi network. Gemini needs internet. AirPods, if used, connect to the phone. The two ESP32 boards communicate through the server; no UART connection between them is required. The laptop remains part of this prototype.

## Components

| Qty | Component | Purpose |
| --- | --- | --- |
| 1 | W11 ESP32-S3 board with OV3660 | Camera capture and image upload; exact PCB revision and pinout must be verified. |
| 1 | ESP32 DevKit V1 with ESP32-WROOM-32 | Distance sensing, local alerts and telemetry. |
| 1 | Standard 5 V HC-SR04 | Coarse forward proximity. |
| 1 | Active 5 V piezo buzzer, ≤30 mA | Audible alerts. |
| 1 | 2N2222A transistor | Buzzer switch; verify the actual package’s lead order. |
| 2 + 1 + 1 | 1 kΩ, 2 kΩ and 10 kΩ resistors, 1% | One 1 kΩ + 2 kΩ ECHO divider; one 1 kΩ base resistor + 10 kΩ pulldown. |
| 1 | Dual-output regulated 5 V USB bank, ≥2 A total | Pocket power; verify operation under combined load. |
| 2 | Board-compatible USB data/power cables | Flashing and power. |
| 1 kit | Glasses frame, perfboard, wire, connectors, heat-shrink, Velcro/cable ties, insulation and enclosure | Mounting and protected wiring; breadboard for bench tests only. |
| 1 each | Laptop, phone, Wi-Fi router/hotspot | Server, audio/UI and network. |

**Tools:** multimeter, soldering iron and access to an oscilloscope for ECHO verification.

**Directional vibration:** rated 5 V motor, AO3400A MOSFET breakout, 100 Ω gate resistor, 100 kΩ pulldown and 1N5819 flyback diode. Verify motor current against driver and supply ratings.

**Trigger fallback:** if the actual HC-SR04 does not reliably accept 3.3 V TRIG, add a 5 V 74AHCT125 buffer with its required support wiring/decoupling.

## Wiring

These GPIO assignments apply to the **second ESP32 DevKit V1**, not the W11.

| Connection | Wiring |
| --- | --- |
| Power | Bank USB → W11 USB; second bank USB → DevKit USB. |
| Sensor power | HC-SR04 VCC → verified USB-derived DevKit 5 V/VIN rail; GND → DevKit GND. Check the clone board’s rail with a meter. |
| TRIG | GPIO18 → HC-SR04 TRIG; verify trigger compatibility on the bench. |
| ECHO divider | ECHO → 1 kΩ → junction → GPIO19; junction → 2 kΩ → GND. Nominally 3.33 V from a 5 V ECHO. Verify before connecting GPIO19. |
| Buzzer | GPIO23 → 1 kΩ → transistor base; base → 10 kΩ → GND; emitter → GND; collector → buzzer negative; buzzer positive → 5 V. |
| Optional motor | GPIO25 → 100 Ω → MOSFET gate; gate → 100 kΩ → GND; source → GND; drain → motor negative; motor positive → regulated 3.0 V, never 5 V. Diode cathode → +3 V, anode → drain. Add the converter/ground/capacitor wiring from the detailed guide. |

All sensor/driver grounds join DevKit GND. Never connect 5 V ECHO directly to a GPIO or apply 5 V to 3V3. Disconnect bank power before laptop flashing.

**W11 verification gate:** obtain the seller’s schematic/example for the exact PCB. Verify camera GPIOs, sensor connector, USB flashing method, flash and PSRAM settings. Do not copy an AI Thinker ESP32-CAM pin map. OV3660 driver support does not establish the W11’s wiring.

## Responsibilities and hardware-first tasks

### Person 1 — Camera, mounting and power

- [ ] Identify the W11 PCB and confirm its pin map and flashing settings.
- [ ] Flash the matching camera example; start at 640 × 480 JPEG.
- [ ] Capture 20 consecutive usable, correctly oriented images without resets.
- [ ] Upload JPEGs with device ID, frame ID and capture time to Person 3’s endpoint.
- [ ] Build the glasses mount and cable harness with Person 2; insulate and secure everything.
- [ ] Test combined power draw, heat and a 15-minute run on the bank.

**Handoff:** verified pin-map reference, working firmware, image-upload contract and mounting/power checks. If camera bring-up is blocked at hour 4, switch to a clearly labeled phone-camera fallback for the demo; retain local obstacle hardware.

### Person 2 — Sensor, alert electronics and firmware

- [ ] Verify supply rails; build the divider and transistor circuit while unpowered.
- [ ] Verify divided ECHO voltage before attaching GPIO19.
- [ ] Send 10 µs trigger pulses every 100 ms; use a 30 ms ECHO timeout.
- [ ] Check readings against a flat target at 30, 60 and 100 cm; median-filter 3 valid samples.
- [ ] Start with slow beeps at 60–100 cm, faster at 30–60 cm and urgent below 30 cm. Add 5 cm hysteresis; calibrate these demo thresholds.
- [ ] Treat no echo as unknown; use a distinct fault indication for prolonged invalid readings. Verify alerts continue without network access.
- [ ] Send telemetry at 5 Hz without blocking sensing. Bring up the 3 V vibration driver after the buzzer works; implement the direction patterns from the detailed guide.

**Handoff:** working sensor/alert firmware, wiring check, calibration results and telemetry fields: device ID, sequence, distance in cm or null, validity and timestamp.

### Person 3 — Software exclusively

- [ ] Build FastAPI endpoints and mocks immediately; do not wait for hardware.
- [ ] Implement route selection, next-checkpoint confirmation, pause and repeat.
- [ ] Store routes, progress and object sightings in SQLite.
- [ ] Build the accessible phone UI, spoken prompts and status dashboard; test on the actual phone.
- [ ] Integrate Gemini object detection with validated output, bounding boxes and explicit not-found/unavailable states. Keep API keys on the laptop.
- [ ] Integrate real images/telemetry; reject stale data and test disconnects.
- [ ] Prepare demo controls and measured latency/results.

**Handoff:** runnable backend/UI, sample route, database and launch instructions. Person 3 performs no wiring, soldering or board flashing. Persons 1 and 2 physically check the demonstration route and supply its instructions.

## Software and integration contract

| Endpoint | Responsibility |
| --- | --- |
| `POST /frame` | Accept JPEG + device/frame ID + capture time; return receipt status. |
| `POST /telemetry` | Accept distance/validity/sequence/time; update device health. |
| `POST /route` | Select route or perform confirm/pause/repeat action. |
| `POST /search` | Search the latest eligible frame for the requested object. |
| `GET /memory` | Return saved routes, confirmed progress and timestamped sightings. |
| `GET /status` | Provide connection state, sensor validity and latency for UI polling. |

Use server-aligned timestamps; reject mismatched or more than 5-second-old search frames, allow one search in flight and report timeouts. Gemini supplies object/scene information; route instructions come from the checked route, not model guesses about a safe path.

Route records contain ordered checkpoints and separately checked forward/return directions. Explicit user/spotter confirmation advances MVP progress. Replaying a saved route does not establish the wearer’s current location.

The local buzzer must remain audible independently of the phone. While connected, fresh obstacle telemetry pauses/ducks phone speech; loss of telemetry produces a disconnected state, not a clear-path indication. HC-SR04 distance must never be presented as the distance to a detected mug or hand.

## Milestones and dependencies

| Hours | Person 1 | Person 2 | Person 3 | Exit condition |
| --- | --- | --- | --- | --- |
| 0–4 | Verify W11 and power | Verify rails/divider | APIs, mocks, route schema | Pinout decision, network/API access and agreed contracts. |
| 4–12 | Camera capture/upload | Local ranging/beeps | Route UI, speech, SQLite; then search | Real images and offline obstacle alerts work separately. |
| 12–24 | Secure mount; check route | Mount sensor; check route | Join hardware and guidance | Complete three-checkpoint navigation demonstration. |
| 24–36 | Power/endurance fixes | Calibration/failure tests | Stale/offline states and rehearsal | Core demo accepted and frozen by hour 36. |
| 36–48 | Reliability/support | Reliability; direction motor checks | Optional features if feasible | Rehearsed final demo; preserve working versions. |

**Critical dependencies:** verified W11 documentation → camera capture → object/scene features; divider/power checks → local alerts; checked route instructions → route guidance. Automatic turns/rerouting additionally need tested localization. Persons 1 and 2 enable Person 3 to work with mocks from hour 0.

## Conditional iPhone and AirPods extension

Confirmed devices are iPhone 14, AirPods Pro 3 and MacBook Air M4. Ordinary speech through AirPods is included. The iPhone 14 has no LiDAR scene depth. Native head tracking/spatial cues require Xcode/signing, headphone-motion permission and verified non-LiDAR anchor/localization methods; W11 images require separate registration. Render audio locally with AVAudioEngine/AVAudioEnvironmentNode; FastAPI handles detection and memory.

Test head turns, phone motion and tracking loss. Compatible AirPods alone do not guarantee sound anchored to a room location. Retain spoken guidance if this extension cannot be demonstrated reliably.

## Acceptance and demo

**Pass before adding stretch:** 15 minutes on bank power without resets; three correct route runs with confirmation/pause/repeat; 10 controlled obstacle approaches; five object searches; stale-frame, no-echo, Wi-Fi-loss and internet-loss checks. Target local warning latency under 0.5 seconds; report measured performance and misses.

**Three-minute demo:** select the checked A → B → C route; play and confirm guidance; introduce a flat obstacle and demonstrate local alerts; replay Route Memory; briefly find a mug as the additional feature; disconnect internet and show local alerts continuing. Use a tabletop walkthrough or sighted wearer with a spotter.

**Known limits:** the single head-mounted ultrasonic sensor can miss small, soft or angled objects and does not cover drop-offs or every hazard. The controlled demo does not validate independent navigation, road crossings or outdoor autonomy. Unknown W11 wiring triggers the camera fallback; cloud failures trigger an unavailable state. Store metadata by default and obtain consent for image uploads.

## Technical references

- [Espressif camera driver and OV3660 support](https://github.com/espressif/esp32-camera)
- [ESP32 electrical specifications](https://documentation.espressif.com/esp32_wroom-32_datasheet_en.pdf)
- [HC-SR04 specifications](https://www.sparkfun.com/ultrasonic-distance-sensor-hc-sr04.html)
- [Gemini image understanding](https://ai.google.dev/gemini-api/docs/image-understanding)
- [ARKit scene reconstruction support](https://developer.apple.com/documentation/arkit/arworldtrackingconfiguration/scenereconstruction)
- [Apple headphone motion](https://developer.apple.com/documentation/coremotion/cmheadphonemotionmanager)
- [Apple spatial audio rendering](https://developer.apple.com/documentation/avfaudio/avaudioenvironmentnode)
