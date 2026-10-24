# Local camera, ultrasonic, and voice demonstration

This development mode runs on a Mac. It uses real YOLO detections and can receive
real distance measurements over USB. Speech plays through the Mac's selected
system output, including paired AirPods. It is separate from the intended hosted
backend/iPhone deployment.

## Camera and object speech

Complete the root README's environment and model setup, select the audio output,
and close other applications using the camera. From the repository root:

```sh
PYTHONPATH=. .venv-phase3/bin/python scripts/preview_live.py --speak
```

The window shows class labels, confidence, and image position. Two consistent
observations enable phrases such as “chair, ahead.” These describe camera image
position, not metric distance or a safe movement direction. P pauses/resumes the
camera; Q/Esc exits and releases resources. Confidence keys +/- affect this
preview only. No images or audio are recorded.

For a prepared W11 local camera, use `--camera-url` with its actual capture URL;
follow [the camera guide](w11-camera.md). The prepared camera's frame-age header
is required for current-scene object speech.

## Ultrasonic sensor-only setup

Identify the separate ESP32 DevKit and actual USB data port using
`arduino-cli board list`. Do not flash the W11 with the DevKit image.
Disconnect power while wiring. Follow [the wiring guide](hardware.md):

| HC-SR04 | Connection |
| --- | --- |
| VCC | Verified USB-derived 5 V rail |
| GND | Common ground |
| TRIG | GPIO18 |
| ECHO | Verified voltage divider to GPIO19; never direct 5 V |

```sh
arduino-cli compile --fqbn esp32:esp32:esp32 --build-property 'compiler.cpp.extra_flags=-DSTRIDE_SELF_TEST=1' --build-path /tmp/stride-bench-sensor firmware/feedback
```

After checking the actual target, rails, and wiring:

```sh
arduino-cli upload --fqbn esp32:esp32:esp32 --port ACTUAL_USB_PORT --input-dir /tmp/stride-bench-sensor firmware/feedback
```

Sensor-only mode disables networking and keeps motor/buzzer outputs OFF. Its
115200-baud serial output includes `STRIDE_SENSOR` JSON measurements. Verify
actual readings with flat targets at measured 100/60/30 cm before demonstrating.
Close the serial monitor before starting a voice bridge; only one process can
own the port.

## Sensor warnings through AirPods

```sh
uv pip install --python .venv-phase3/bin/python -r scripts/requirements-hardware.txt
PYTHONPATH=. .venv-phase3/bin/python scripts/serial_voice.py --port ACTUAL_USB_PORT
```

The bridge prints state/distance and uses macOS speech. Ctrl-C stops it;
`--mute` prints events without speaking. Confirm the phrase is actually heard
through the intended output. Software readiness does not prove AirPods routing.

The vocabulary includes:

- “Stop. Object nearby.”
- “Caution. Object nearby. Stop and check your path.”
- “Distance sensing unavailable. Stop and check.”
- “Distance warning cleared. Check your path before moving.”

Host warning bands are 50/100 cm with hysteresis. Recovery requires three valid
readings above 105 cm. Measurements expire after one second, duplicate uptime
never renews health, and unresolved warnings repeat no more often than every five
seconds. Invalid/no-echo/out-of-range readings are unknown, never infinite clear
space. These are uncalibrated demonstration defaults.

## Combined sensor and object audio

Stop the standalone serial bridge and old camera preview first, then:

```sh
PYTHONPATH=. .venv-phase3/bin/python scripts/preview_live.py --sensor-port ACTUAL_USB_PORT
```

Sensor danger, caution, or unknown interrupts/suppresses object narration.
Recovery speech must finish before fresh object descriptions resume. P pauses
only the camera; sensor warnings continue. Q/Esc releases camera, serial, and
speech. A forward range cannot identify a chair, determine which recognized
object produced an echo, or establish safe left/right avoidance.

Camera inference and sensor polling share this diagnostic's UI loop, so no
independent warning-latency guarantee is claimed. The sensor-only image has no
physical buzzer/motor warning enabled. Keep the demo controlled and supervised.

## Physical acceptance checks

1. Record range accuracy/variation at measured target distances.
2. Confirm a real approaching target produces an audible warning.
3. Test invalid/no-echo and serial disconnection; neither may imply safe movement.
4. Verify recovery gives no automatic movement instruction.
5. Test protected motor/buzzer circuits separately using the
   [firmware guide](../firmware/README.md) before enabling physical outputs.

A successful compile or mocked speech test does not establish these physical
results. Record actual observations separately from software regression tests.
