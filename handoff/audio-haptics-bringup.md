# Stride — get detection, audio and motor feedback running

Confirmed: the 3 V part is a **vibration motor**, not a buzzer. You can bring up local sensor/motor feedback without buying a buzzer. A motor vibrates; AirPods provide spoken audio. Neither ESP32 connects directly to AirPods.

## 1. Hear real detections on Mac now

Close the existing webcam preview with Q/Esc before starting another capture. Pair/connect AirPods to the Mac and select them under Control Center → Sound (or System Settings → Sound → Output). The preview uses the selected system output; it cannot verify which headphones receive it. [Apple connection/output instructions](https://support.apple.com/en-us/108786).

Easiest: double-click `Start_Stride_Demo.command` in this repository. It selects the checkout folder and prepared interpreter and keeps startup errors visible. Alternatively, from this prepared checkout:

```sh
cd /Users/adhyannsingal/Documents/Codex/2026-10-22/referenced-chatgpt-conversation-this-is-an/stride
PYTHONPATH=. /tmp/stride-phase2-venv/bin/python scripts/preview_live.py --speak
```

That Python path is available on this machine. Other machines use README environment/model setup and their own Python executable. No new model or cloud account is needed for this local diagnostic. The matching ignored ONNX artifact must exist.

Hold/move supported objects in view: two consistent detections allow short phrases such as “chair, ahead” or “cup, to the left.” These describe image position, not measured depth or a safe avoidance direction. The preview speaks through macOS `/usr/bin/say`, runs inference locally and does not use Gemini. No inference backlog or speech queue is added. Persistent objects are not narrated every frame. Pause with P; Q/Esc quits and releases camera/audio. Invalid/dark/stale input suppresses local object speech. Very slow/blocking capture/inference can still delay the preview loop's cancellation checks; this diagnostic is not a certified warning loop.

No “move right” is generated from a chair box. A checked route can independently say “turn right at checkpoint B”; nearby ultrasonic readings drive separate local stop/proximity patterns. One forward sensor cannot establish left/right free space or associate its range with a particular detected chair.

This is a local object-awareness audio demo. It has no sensor/route speech arbitration and must not be presented as integrated spoken navigation. Actual AirPods routing/audibility, false positives/misses and walking behavior require observation. No camera images are recorded by the preview.

## 2. Connect the ultrasonic sensor first

Use the **separate ESP32 DevKit V1**, not W11 GPIOs. Disconnect power before wiring and check the actual rail labels on your clone.

| HC-SR04 | DevKit connection |
| --- | --- |
| VCC | Verified USB-derived 5 V |
| GND | GND |
| TRIG | GPIO18; verify 3.3 V trigger works with your sensor |
| ECHO | 1 kΩ → junction → GPIO19; junction also connects through 2 kΩ to GND |

Never connect 5 V ECHO directly to GPIO19. Verify divider voltage with a safe DC test or oscilloscope before attaching the GPIO; a meter's average pulse reading is insufficient. Nominal divider output is 3.33 V at 5.0 V input; verify your actual supply/output against ESP32 limits. See [the full circuit and power guide](../Stride_Hardware_Wiring_Guide.md).

No Wi-Fi credentials are needed for the independent bench modes. The provided Arduino CLI on this machine is `/tmp/stride-arduino/arduino-cli`; otherwise use an installed `arduino-cli`.

```sh
/tmp/stride-arduino/arduino-cli board list
/tmp/stride-arduino/arduino-cli compile --fqbn esp32:esp32:esp32 --build-property 'compiler.cpp.extra_flags=-DSTRIDE_SELF_TEST=1' --build-path /tmp/stride-bench-sensor firmware/feedback
```

After checking board identity/wiring/rails, substitute its **actual** USB serial port below (do not use Bluetooth/debug ports):

```sh
/tmp/stride-arduino/arduino-cli upload --fqbn esp32:esp32:esp32 --port ACTUAL_USB_PORT --input-dir /tmp/stride-bench-sensor firmware/feedback
/tmp/stride-arduino/arduino-cli monitor --port ACTUAL_USB_PORT --config baudrate=115200
```

Sensor-only mode reports valid/median distance/band while motor/buzzer outputs remain off. Check flat targets around 100, 60 and 30 cm, then no-echo/invalid behavior. Do not claim measured distance before this actual test.

## 3. Add the protected 3 V motor

Required: regulated 3.0 V supply with adequate startup/stall current, suitable 3.3 V gate MOSFET driver (specified AO3400A breakout), flyback diode and suppression components. If these are missing, stop at sensor-only; don't connect the motor directly to ESP32 GPIO, 5 V or the board's 3V3 rail.

```text
Verified 5 V → buck converter set/measured to 3.0 V → motor positive
Motor negative → MOSFET DRAIN
MOSFET SOURCE → common GND
GPIO25 → 100 Ω → MOSFET GATE
GATE → 100 kΩ → GND

1N5819 diode across motor:
  striped CATHODE → motor positive (+3 V)
  ANODE → motor negative / drain
100 nF ceramic across motor terminals
100 µF + 100 nF across the regulated rail near the driver
DevKit GND, converter ground and sensor GND common
```

Verify the actual breakout pinout; measure 3.0 V before connecting the motor and recheck under load. Do not join independent 5 V rails/backfeed USB. See the full wiring guide for supply capacity and mounting requirements.

Run motor-only bench mode first: repeat compile/upload above with `STRIDE_SELF_TEST=3` and `/tmp/stride-bench-motor` as build/input directory. It waits 2 seconds, emits **one 100 ms pulse**, then stays off. The sensor need not be connected in this mode. Stop the serial monitor before uploading. Check voltage, motor operation and board resets.

Once sensor and motor pass separately, compile normal mode **without** the self-test flag:

```sh
/tmp/stride-arduino/arduino-cli compile --fqbn esp32:esp32:esp32 --build-path /tmp/stride-feedback firmware/feedback
/tmp/stride-arduino/arduino-cli upload --fqbn esp32:esp32:esp32 --port ACTUAL_USB_PORT --input-dir /tmp/stride-feedback firmware/feedback
```

With network unconfigured, this is a local sensor→motor test. Move a flat target through the uncalibrated 100/60/30 cm bands and verify warning patterns, filtered response delay and offline operation. GPIO23 can remain unconnected if no buzzer is fitted.

**Current motor-only limitation:** unknown/no echo leaves the motor off and requests a periodic beep on GPIO23. Without a buzzer you cannot feel/hear that fault from these outputs. An inactive motor is not proof of clear space. Check serial/status; a distinct motor-only fault vocabulary is a separate firmware change requiring validation. No fault-vibration feature is claimed here.

## 4. Add backend commands and the phone/AirPods path

- Agent 1's implemented Phase 4 API supplies pairing, telemetry, command/ACK and obstacle route blocking; see [DEVICE_INTEGRATION.md](../backend_phase3/DEVICE_INTEGRATION.md). Configure ignored `firmware/feedback/secrets.h` with an actual HTTPS URL, device token, session/device IDs, Wi-Fi credentials and CA. Pair the controller to its authorized session. Do not use insecure TLS or invent credentials.
- Agent 3 tests actual ESP32 HTTPS exchange and command expiry/preemption. Left/right/straight patterns are checked-route cues; one motor represents learned patterns, not physical left/right location. Local proximity alerts always win and work without the network.
- Agent 1/2 still need final authorized speech events and real frontend/API compatibility. Once ready, iPhone viewer joins the same session, enables audio with a tap and uses iOS-selected AirPods output. Existing Mac preview speech does not implement that phone workflow. Stop local preview when browser/W11 becomes the selected capture source.
- W11 is a separate final step: verified board/camera pins and memory settings, vendor camera example, then resolve missing camera-state and raw-JPEG versus multipart compatibility before claiming server uploads. Don't flash a syntax-only camera binary.

## Verification status for this change

43 vision/integration tests passed, 2 optional fixture tests skipped; new tests cover stabilization, no speech backlog, expiry, disappearance and pause cleanup. Mocked speech tests establish scheduling behavior, not actual Bluetooth playback. The actual macOS speech-process smoke exited 0 for “Stride audio test.” This does not confirm which output device received it or whether the user heard it. USB enumeration showed only Bluetooth/debug serial entries, with no ESP32 USB board identified; no port was invented or flashed. No ESP32 flash, rail measurement, physical sensor/motor check or AirPods test is implied by passing software tests.

## Speech startup correction

The original preview incorrectly cancelled each macOS speech process after one second. Direct phrases took 2.887 s and 2.190 s in the reproduction, so this could prevent audible output. The corrected preview renews the speech evidence only while newer fresh frames still show the same class/image sector, cancels on disappearance or stale input, and caps each voice process at 5 seconds. Added regressions cover startup longer than one second and the absolute cap. Actual audibility still requires human confirmation.
