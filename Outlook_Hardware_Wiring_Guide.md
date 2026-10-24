# Outlook hardware wiring guide

**Build:** navigation assistance glasses; W11 ESP32-S3/OV3660 camera plus a separate ESP32 DevKit V1 for sensing and feedback.

**Confirmed equipment:** MacBook Air M4, standard iPhone 14, AirPods Pro 3 and a simple 3 V vibration motor. Verify actual component availability at sprint kickoff; earlier delivery estimates are not proof the parts are on hand.

Use the six-hour `buildspec_outlook.md` for schedule, software ownership and hosted runtime. This guide controls electrical connections and supersedes the earlier 5 V vibration-motor suggestion. **Your motor is rated 3 V.** Use the sensor board's GPIO labels, not physical header positions; DevKit clones vary. The W11 camera pin map remains unverified.

## 1. What goes where

| Part | Location |
| --- | --- |
| W11 and supplied camera | Front of glasses, above one lens; use its original connector/cable. |
| HC-SR04 | Front beside camera, level; both transducers unobstructed. |
| DevKit, driver circuits and motor regulator | Insulated collar enclosure. |
| Buzzer | Collar, away from ear. |
| Vibration | One motor on wrist for pattern testing; preferably one on each wrist for left/right directions. |
| USB power bank | Pocket; two separate USB outputs/cables to the two boards. |
| iPhone | Controls and AirPods audio; not a source of LiDAR depth. |
| MacBook | Development only; final wearable uses the hosted backend. |

Run the harness along the glasses arm and down the collar, with slack and strain relief. Label wrist connectors L/R. Insulate exposed conductors; make the power connection easy to disconnect. Keep antennas clear of metal and check heat, weight and comfort before wearing.

## 2. Bill of materials

### Required for sensing and audio alerts

- 1 W11 ESP32-S3 with OV3660 and correct USB cable; exact revision must be documented.
- 1 ESP32 DevKit V1 using ESP32-WROOM-32; USB data cable.
- 1 standard 5 V HC-SR04.
- 1 active **piezo** 5 V buzzer drawing at most 30 mA.
- 1 2N2222A transistor; confirm its actual base/collector/emitter pin order.
- 2 × 1 kΩ resistors, 1 × 2 kΩ and 1 × 10 kΩ, preferably 1%.
- 1 regulated dual-output 5 V USB bank, at least 2 A combined; validate with the actual load.
- Perfboard, connectors, wire, insulation, removable mounts and enclosure. Breadboard for bench work only.
- Multimeter; access to an oscilloscope or safe DC test arrangement to verify ECHO divider output.

### Required for your 3 V vibration motor

For **each** channel: 1 motor rated 3 V, 1 AO3400A N-channel MOSFET breakout exposing gate/drain/source, 1 × 100 Ω gate resistor, 1 × 100 kΩ gate pulldown, 1 × 1N5819 flyback diode and 1 × 100 nF ceramic capacitor across motor terminals.

Shared: 1 regulated **5 V to 3.0 V buck converter**, with current capacity exceeding the combined motor startup/stall demand plus margin; a 1 A continuous-rated unit is a starting selection, not a verified motor-current measurement. Add 100 µF electrolytic plus 100 nF ceramic across its 3 V output near the drivers; follow the converter manufacturer's capacitor requirements too.

One motor is enough to test patterns now. Two matching motors and two complete driver channels give clearer physical left/right feedback. Do not buy a second motor until the first motor's rating/current and the driver's pinout are checked.

## 3. Power wiring

```text
Power bank output A ── USB cable ── W11 USB input
Power bank output B ── USB cable ── DevKit USB input
                                        │
                           verified USB-derived 5 V rail
                             ├── HC-SR04 VCC
                             ├── buzzer positive
                             └── buck VIN+ → regulated 3.0 V → motor positive(s)

DevKit GND ── sensor GND, transistor emitter, buck VIN−/VOUT−,
              motor MOSFET source(s), divider and pulldown grounds
```

1. With everything disconnected, inspect the boards and identify their labeled rails.
2. Power DevKit by USB alone. Measure its proposed 5 V/VIN rail relative to GND; confirm that USB powers this rail on your clone and its current path can support the planned load.
3. Set the buck converter to **3.0 V** with a meter **before attaching a motor**. Recheck under load. If a converter is isolated, explicitly join its output negative to DevKit GND.
4. Connect sensor and drivers incrementally; do not route motor return current through the thin ECHO-divider ground wire.
5. If rail current capacity is insufficient, use a documented separate protected 5 V distribution branch for loads, sharing GND; do not backfeed the board's 5 V pin while USB is also connected.

**Never:** connect a motor directly to a GPIO; put a 3 V motor on 5 V; assume the DevKit's 3V3 regulator can power motors; join two independent 5 V output rails; power a board by USB and an external 5 V pin without a verified power-path design. Disconnect bank power before flashing from the Mac.

## 4. HC-SR04 wiring

| Sensor pin | Destination |
| --- | --- |
| VCC | Verified 5 V rail |
| GND | DevKit GND |
| TRIG | GPIO18; bench-test 3.3 V trigger acceptance |
| ECHO | Divider below; **never directly GPIO19** |

```text
HC-SR04 ECHO ── 1 kΩ ──●── GPIO19
                      │
                    2 kΩ
                      │
                     GND
```

The junction is nominally 3.33 V for a 5.0 V input. Check actual supply and divider output before connecting GPIO19; ESP32 inputs are not 5 V tolerant. Verify the divider using a safe 5 V DC test with the sensor disconnected, or observe actual pulses with a scope. A multimeter's average reading of short ECHO pulses is not a reliable peak-voltage check.

Use a 10 µs trigger, 100 ms measurement interval and 30 ms echo timeout. Start calibration with a flat target at 30, 60 and 100 cm. No echo is unknown, not a guarantee that the path is clear. A single range measures a forward cone, not object identity, hand distance or a left/right free path.

### If TRIG needs a 5 V buffer

Use a **SN74AHCT125 in a verified 14-pin package**, not an arbitrary bidirectional I²C shifter. For the standard 14-pin mapping: pin 14 → 5 V; pin 7 → GND; 100 nF between pins 14/7; pin 1 (1OE) → GND; GPIO18 → pin 2 (1A); pin 3 (1Y) → TRIG. Disable unused channels: pins 4/10/13 → 5 V; unused inputs 5/9/12 → GND; outputs 6/8/11 unconnected. Verify package orientation against TI's diagram before power-up.

## 5. Buzzer wiring

```text
GPIO23 ── 1 kΩ ── BASE of 2N2222A
                    │
                  10 kΩ
                    │
                   GND
EMITTER ── GND
COLLECTOR ── buzzer negative
5 V ── buzzer positive
```

Use the rated active piezo part specified above. Initialize GPIO23 LOW at boot. Transistor package lead orders vary: identify terminals from the exact part datasheet rather than a generic photo. An electromagnetic buzzer needs its own inductive-load protection.

## 6. Vibration wiring

Repeat this circuit per motor:

```text
GPIO25 LEFT / GPIO26 RIGHT ── 100 Ω ── GATE
                                         │
                                       100 kΩ
                                         │
                                        GND
MOSFET SOURCE ── GND
MOSFET DRAIN ── motor negative
regulated 3.0 V ── motor positive

1N5819 across motor: striped CATHODE → +3 V; ANODE → motor negative/drain
100 nF ceramic directly across motor terminals
```

Use AO3400A breakouts with a confirmed 3.3 V gate-compatible design. Verify G/D/S labeling; do not assume raw SOT-23 lead order. Power off while assembling. The flyback diode stripe must face motor positive. Start with a short 100 ms test and check converter voltage, startup, driver heat and board resets.

| Guidance event | Two motors | One motor fallback |
| --- | --- | --- |
| Left | Left, 2 × 150 ms pulses, 150 ms gap | 1 × 200 ms pulse |
| Right | Right, 2 × 150 ms pulses, 150 ms gap | 2 × 200 ms pulses, 200 ms gap |
| Straight | Both, 1 × 150 ms pulse | 3 × 120 ms pulses, 120 ms gaps |
| Stop / nearby obstacle | Both, 3 × 200 ms pulses, 150 ms gaps; buzzer alert | 1 × 800 ms pulse plus buzzer alert |

These are initial patterns to test with users, not a validated vocabulary. A single motor has no physical left/right distinction; it relies on learning patterns. Directions originate from the checked route, not from HC-SR04 range. Stop takes priority, cancels queued turns and expires rather than vibrating indefinitely. Initialize both motor GPIOs LOW.

## 7. W11 camera wiring gate

No external sensor/motor GPIOs are needed on the W11. Power via its verified USB input and keep the supplied camera ribbon installed correctly. Before flashing, Person 1 must record:

| Item | Required verification |
| --- | --- |
| Board | PCB markings/revision, front/back photos, seller documentation |
| Camera | OV3660 identification and ribbon orientation |
| Camera configuration | D0–D7, XCLK, PCLK, VSYNC, HREF, SCCB SDA/SCL, PWDN/RESET if present |
| Memory/toolchain | Actual flash/PSRAM size and mode, board settings, upload/boot method |

**Do not substitute AI Thinker pin definitions or invent a W11 map.** Use a matching seller example first. Start with 640 × 480 JPEG and pass 20 captures without resets. Share the board markings/schematic when it arrives so the remaining board-specific pin configuration can be finalized.

## 8. Integration sequence and owners

1. **Person 1:** W11 identification, USB power and camera-only example.
2. **Person 2:** DevKit rails, divider and sensor-only ranging; no motors yet.
3. **Person 2:** buzzer driver, then one motor, then second motor. Check rails after each addition.
4. **Persons 1/2:** common enclosure, harness and mounting; inspect all wiring unpowered.
5. **Person 3, software only:** substitute real frame/telemetry adapters for mocks and send expiring direction commands.
6. **Person 2:** verify alert timing is nonblocking, old commands cannot replay and motors go off on link loss. Local obstacle alerts remain active without the backend.
7. **All:** 15-minute powered run, disconnect/reconnect tests, 10 approaches to staged flat targets and direction-pattern checks. No unsupervised navigation trials.

## 9. AirPods connections

AirPods connect by Bluetooth to the Mac tonight and to the iPhone when using the phone UI/native app. They do not require ESP32 audio wiring. Keep spoken guidance and buzzer audible together. Use Transparency mode and a modest volume for supervised tests.

The standard iPhone 14 has no rear LiDAR. AirPods Pro 3 support head-tracked Spatial Audio, but native headphone-motion access, app coordinates and calibration still need testing. Ordinary spoken instructions are included; room-anchored object sound is an extension to prove.

## References

- [ESP32 electrical specifications](https://documentation.espressif.com/esp32_wroom-32_datasheet_en.pdf)
- [Espressif camera driver](https://github.com/espressif/esp32-camera)
- [HC-SR04](https://www.sparkfun.com/ultrasonic-distance-sensor-hc-sr04.html)
- [AO3400A manufacturer specifications](https://www.aosmd.com/products/mosfets/low-voltage-mosfets-12v-30v/ao3400a)
- [Motor driver and flyback diode example](https://learn.adafruit.com/adafruit-arduino-lesson-13-dc-motors?view=all)
- [SN74AHCT125 datasheet](https://www.ti.com/lit/ds/symlink/sn74ahct125.pdf)
- [iPhone 14 specifications](https://support.apple.com/en-us/111850)
- [AirPods Pro 3 specifications](https://www.apple.com/airpods-pro/specs/)
