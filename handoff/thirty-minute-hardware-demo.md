# Deadline hardware/voice demo

Mac-assisted fallback: HC-SR04 -> ESP32 -> USB serial -> Mac speech -> selected
AirPods audio output. This is not the final hosted/iPhone runtime. No sensor can
identify a chair or infer a safe avoidance side from this forward range alone.

## Bring-up

1. Verify ESP32-WROOM/DevKit identity and wiring with power disconnected.
   VCC to verified 5 V, GND common, TRIG GPIO18, ECHO through verified 1k/2k divider
   to GPIO19. See Stride_Hardware_Wiring_Guide.md. Never connect ECHO directly.
2. Sensor-only build keeps buzzer/motor outputs OFF and networking disabled:

```sh
/tmp/stride-arduino/arduino-cli compile --fqbn esp32:esp32:esp32 --build-property 'compiler.cpp.extra_flags=-DSTRIDE_SELF_TEST=1' --build-path /tmp/stride-deadline-sensor firmware/feedback
```

3. After identity/wiring/actual port verification, upload that artifact using
   arduino-cli upload with the actual port. Do not flash a W11 with this image.
   Release BOOT after upload; press EN/RESET if necessary. Close serial monitors
   before launching the bridge; only one process owns the serial port.
4. Pair/select AirPods in macOS. System output selection does not prove the wearer
   hears the voice: explicitly confirm the audible test phrase.

```sh
uv pip install --python /tmp/stride-phase2-venv/bin/python -r scripts/requirements-hardware.txt
PYTHONPATH=. /tmp/stride-phase2-venv/bin/python scripts/serial_voice.py --port ACTUAL_USB_PORT
```

Use Ctrl-C to stop speech/bridge. `--mute` prints events without speaking.
The script stores no images/audio, prints distance/state, drops serial backlog,
uses only newest complete measurement, and interrupts previous speech on a state
change. No read/no echo/out-of-range means unknown, never an infinite clear path.
Repeated identical uptime does not renew freshness. Host distance warnings use
50/100 cm with hysteresis, require three readings >105 cm for recovery, expire
after 1 second and repeat unresolved warnings at most every 5 seconds.

Voice vocabulary: "Stop. Object nearby", "Caution. Object nearby. Stop and check
your path", "Distance sensing unavailable. Stop and check", and "Distance warning
cleared. Check your path before moving". Never automatic "move left/right".
Local controller median filtering adds latency and its 30/60/100 cm bands differ
from the host's conservative range warnings. These are uncalibrated demo defaults.

## Physical acceptance before claiming success

- Flat target at measured 100/60/30 cm: record actual serial ranges/variation.
- Move target closer: hear real near-object warning through actual AirPods.
- Remove/angle target: invalid/no echo must not announce safe movement.
- Unplug/disconnect serial: hear sensing-unavailable warning.
- Recover: no automatic movement instruction.
- Local buzzer/motor checks require the protected circuits and a separate verified
  build; sensor-only mode deliberately does not test those drivers.

Software evidence: sensor-only compile succeeded; 2 focused voice-policy tests
pass for stop/staleness/recovery/invalid readings/repeats. Actual USB upload,
real ranges and audible AirPods confirmation must be recorded separately once
observed. The initial USB adapter enumerates as CP210x at cu.usbserial-0001;
chip probe is currently failing and requires boot/connection troubleshooting.
