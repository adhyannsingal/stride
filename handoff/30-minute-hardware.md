# Stride — 30-minute hardware bring-up

## Build only this now

- Separate DevKit V1 + HC-SR04: real distance readings over USB serial.
- W11 with its supplied camera ribbon: camera-only bring-up after exact board identification.
- Existing Mac webcam + YOLO + spoken audio remains the working demonstration until W11 is independently proved.
- Leave motor, buzzer and their GPIO23/25 outputs disconnected. No driver is available. No external connections between the two ESP32 boards.

## Minutes 0–5: unpowered wiring

Use USB data cables. DevKit is the ESP32-WROOM board; W11 is the separate ESP32-S3 camera board. Use GPIO labels, not header position numbers.

| HC-SR04 pin | DevKit |
|---|---|
| VCC | Verified USB-derived 5 V rail (often labeled VIN/5V; check your clone) |
| GND | GND |
| TRIG | GPIO18 |
| ECHO | 1 kΩ resistor to junction; junction to GPIO19; 2 kΩ from junction to GND |

```text
HC-SR04 ECHO ── 1 kΩ ──●── GPIO19
                      │
                    2 kΩ
                      │
                     GND
```

Two 1 kΩ resistors in series can form the 2 kΩ lower leg: three 1 kΩ resistors total. Do not connect 5 V ECHO directly to GPIO19. Verify the divider output against the actual ESP32 input limits before attaching the input. Never use a motor or bare 5 V GPIO load. Power via USB only for bench bring-up.

## Minutes 5–12: sensor-only firmware

From this prepared checkout:

```sh
cd /Users/adhyannsingal/Documents/Codex/2026-10-22/referenced-chatgpt-conversation-this-is-an/stride
/tmp/stride-arduino/arduino-cli board list
/tmp/stride-arduino/arduino-cli compile --fqbn esp32:esp32:esp32 --build-property 'compiler.cpp.extra_flags=-DSTRIDE_SELF_TEST=1' --build-path /tmp/stride-bench-sensor firmware/feedback
```

Identify the DevKit's actual new USB port by connecting it alone; Bluetooth and debug-console ports are not its upload target. After board identification and wiring checks, substitute that port:

```sh
/tmp/stride-arduino/arduino-cli upload --fqbn esp32:esp32:esp32 --port ACTUAL_DEVKIT_USB_PORT --input-dir /tmp/stride-bench-sensor firmware/feedback
/tmp/stride-arduino/arduino-cli monitor --port ACTUAL_DEVKIT_USB_PORT --config baudrate=115200
```

If upload is waiting for connection, use your DevKit's documented BOOT/EN sequence; do not apply guessed W11 boot settings. Stop the serial monitor before any later upload. No network config is needed in sensor bench mode. Both actuator outputs remain OFF.

Expected output is `sensor valid=1 median_cm=... band=...`; bands are 0 unknown, 1 clear, 2 warning, 3 near, 4 stop. Filtering needs three valid samples. Check a flat object around 100/60/30 cm; invalid/no echo should report unknown. These are uncalibrated defaults, not navigation safety thresholds.

This verifies physical sensing only. Bench serial output does not automatically enter the backend or the existing object-preview speech. Don't claim integrated sensor speech from seeing serial readings.

## Minutes 5–20, in parallel: identify and bring up W11

Keep the supplied camera/ribbon connected in its original orientation; do not add external camera signal wiring. Power only from its verified USB connector. Record board front/back markings, vendor/product link, exact revision and any supplied example. N16R8 or OV3660 alone does not establish a PCB pin map.

The repository intentionally blocks unverified W11 builds. Its existing syntax-only camera binary cannot initialize a camera and must not be flashed. Do not set STRIDE_W11_VERIFIED=true or substitute another board's map just to compile.

Once positively matched, run the matching vendor camera-only example first with its verified flash/PSRAM/USB settings. Validate 20 correctly oriented images without reset. If the verified example exposes a stream, use its reported address and test the stream before adapting the existing vision client; do not invent a URL/port or assume it works.

Current integration blockers are explicit: W11 firmware uses raw JPEG + camera-state polling, while the implemented backend uses multipart /frame and lacks that camera-state endpoint. A correct PCB pin map alone does not resolve the API mismatch. Agent 1 owns server compatibility; Agent 3 owns camera/client adaptation. Use one agreed path rather than another app.

## Minutes 20–30: freeze and demonstrate

- If W11 bring-up/protocol isn't verified by minute 20, retain the real laptop camera, clearly labeled; no submission-time firmware gamble.
- Show real DevKit ultrasonic serial readings and the independently working live YOLO/audio preview. Disclose that these are separate verified components until actually connected end to end.
- If W11 is proved, switch the selected capture source explicitly and recheck detections/audio before claiming glasses operation.
- Mount only after unpowered inspection and stable power checks: W11/sensor front of glasses, DevKit insulated at collar, cables strain-relieved. USB bank can replace Mac power after the bench check; no motor driver or haptics is claimed.
- Record exactly what works: local visual/audio, actual sensor readings, W11 source if proved, unresolved integration. Use a stationary/controlled supervised demo; no inferred left/right avoidance.
