# Agent 3 firmware

Current source is compiled against Arduino-ESP32 **3.3.2**, ArduinoJson **7.4.2**.
Arduino CLI used: 1.5.2-rc.1. No hardware was flashed or physically validated.

## Build and tests

From repository root, with Arduino CLI installed:

```sh
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@3.3.2 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli lib install ArduinoJson@7.4.2
firmware/check.sh
clang++ -std=c++17 -Wall -Wextra -Werror tests/vision/controller_test.cpp -o /tmp/stride-controller-test
/tmp/stride-controller-test
```

Set `ARDUINO_CLI` if the executable is outside PATH. The tool downloaded in this
session is `/tmp/stride-arduino/arduino-cli`. check.sh compiles DevKit with
`esp32:esp32:esp32`, validates uploader syntax with `esp32:esp32:esp32s3` and
`-DSTRIDE_CAMERA_COMPILE_ONLY`, and confirms an unconfigured real W11 build fails.
**The camera syntax binary cannot initialize a camera. Do not flash it.** Exact
W11 flash/PSRAM/USB/FQBN options remain unknown until vendor evidence is supplied.
No guessed board configuration was used to obtain the syntax-only result.

## Private configuration

Copy each `secrets.example.h` to ignored `secrets.h`. Supply Wi-Fi SSID/password,
HTTPS origin, session/device IDs, device-role token, PEM root CA and set
`STRIDE_NETWORK_CONFIGURED=true`. Never print tokens or commit these files. Local
feedback works without network config. Camera uploads stay disabled without it.
TLS verifies CA and NTP time; no `setInsecure` workaround exists.

Agent 1 must ensure the shared .gitignore includes firmware/**/secrets.h,
firmware/**/board_config.h, models/*.pt, models/*.onnx and private captures.

## DevKit

GPIO18 TRIG; GPIO19 divided ECHO; GPIO23 switched buzzer; GPIO25 MOSFET-switched
regulated 3 V motor. Full circuits and human measurement sequence are in the
root wiring guide. Serial 115200 reports local-only mode, network-task failures
and full ACK buffers, without credentials.

The local loop uses an edge interrupt, 10 us trigger, 100 ms sample interval,
30 ms timeout and median of three valid readings. Invalid/no echo is unknown;
warning/near/stop bands use 100/60/30 cm and 5 cm hysteresis. The native policy
has distinct one-motor patterns, TTL/ID bounds and local-warning priority.

A separate task performs bounded TLS telemetry, command polling and ACK transport.
It now matches [Phase 4's implemented API](../backend_phase3/DEVICE_INTEGRATION.md):
`X-Device-Token`, `/telemetry`, `/devices/{id}/commands` and `/devices/{id}/ack`.
Telemetry sends device_id/boot_id/sequence/uptime_ms/measurement_valid/distance_cm
and source=real. Session association is authorized pairing on the backend, not
selected by the telemetry body. Provision a separate controller secret and have
the authorized UI/operator call `/device/pair` before controller operation.

Command parsing verifies device/session/boot, delivered status, navigation ID,
nonnegative revision, known kind and 1..1500 ms remaining TTL. The backend checks
current revision and expiry during the received ACK BEFORE the cue reaches the
local loop. Poll plus ACK elapsed time and queue delay are subtracted from TTL.
Stop/cancel never disable local sensor warnings. Network-health age >1 s cancels
remote patterns. Queues remain bounded (one cue, eight terminal ACKs); the local
controller keeps a bounded ID ledger and rejects repeats. A lost one-shot command
or failed receipt ACK drops the optional cue. Terminal ACKs are retried without
re-execution; they report software execution, never verified motor movement.
The ID ledger fails closed when full until device reboot; sample counters/uptime
are extended to 64 bits. TLS responses require bounded Content-Length <=4096;
unknown/chunked responses fail closed and need compatible proxy configuration.

Host-side tests decode an actual API command using the SAME firmware parser and
check identity/status/expiry/revision failures. The complete sketch is compiled.
This does not prove ESP32 TLS/Wi-Fi timing or physical motor/sensor operation.
Local bands (100/60/30 cm) differ from conservative backend holds (100/50 cm);
both are uncalibrated demonstration defaults. Backend clear is never safe-path
proof. Local warning timing includes median filtering; measure actual latency.

## W11

Copy `camera/board_config.example.h` to ignored `board_config.h` only after
verifying exact PCB revision/vendor GPIOs, sensor connector, memory/boot settings,
XCLK and upright unmirrored orientation. Set `STRIDE_W11_VERIFIED=true` only after
that check. The default intentionally fails compilation. Sensor ID must be OV3660.
Use the vendor example to prove 20 usable correctly oriented captures first.

Uploader requests device-authorized `/devices/{id}/camera-state` before every
capture; wrong/inactive/retired/unreachable state suppresses uploads. It estimates
server clock offset using RTT <=200 ms. Driver first-DMA timestamps are aligned
from boot time, not restamped at upload. JPEG VGA, one framebuffer, latest grab,
raw POST <=1 MB, canonical metadata including X-Source-Revision. Every capture
path returns its buffer; failed uploads are dropped with no retry backlog.
Nominal loop pacing is 200 ms; actual sustained rate/age must be measured on W11.
TLS handshakes/network load may prevent the target rate. This is not a measured
5 Hz device guarantee. Camera bring-up, compile with verified pins and actual
uploads remain BLOCKED by board facts and backend compatibility: Phase 4 still lacks
the camera-state endpoint and expects multipart frames, while this uploader uses
raw JPEG. Do not claim W11 end-to-end compatibility from a syntax compile.

## Physical checklist (human Adhyann)

1. Identify PCB/camera; verify USB-derived rails and power paths unconnected.
2. Verify ECHO divider safely before GPIO19; sensor only at 30/60/100 cm.
3. Test switched buzzer, then motor with measured regulated 3.0 V and protection.
4. Check offline local alerts and that old remote cues do not replay after recovery.
5. Validate vendor camera example; bind W11 session; test continuous hosted uploads.
6. Combined load/heat/reset test, insulated enclosure and strain relief; 15-minute run.
7. Controlled route with sighted spotter; record actual output and misses separately.

References: [Espressif camera driver](https://github.com/espressif/esp32-camera),
[Wi-Fi API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/wifi.html),
[ArduinoJson 7](https://arduinojson.org/v7/api/jsondocument/).

## Independent component self-tests

No backend is required. All three bench modes disable the network task and remote
commands. Compile the one mode needed, then flash only the physically checked
DevKit using its actual USB port (board inventory is still pending):

```sh
arduino-cli compile --fqbn esp32:esp32:esp32 --build-property 'compiler.cpp.extra_flags=-DSTRIDE_SELF_TEST=1' --build-path /tmp/stride-bench-sensor firmware/feedback
# Change STRIDE_SELF_TEST to 2 for buzzer or 3 for motor.
# After a human verifies the target/rails/wiring:
# arduino-cli upload --fqbn esp32:esp32:esp32 --port ACTUAL_USB_PORT --input-dir /tmp/stride-bench-sensor firmware/feedback
arduino-cli monitor --port ACTUAL_USB_PORT --config baudrate=115200
```

Mode 1 logs sensor validity, median cm and band at 10 Hz; motor/buzzer stay OFF.
Start with sensor-only wiring and the verified ECHO divider. Modes 2 and 3 keep
TRIG and the unused driver LOW, wait 2 seconds, issue one 100 ms pulse and remain
OFF thereafter. They do not automatically repeat; reset only for an intentional
new bench test. Mode 3 requires the measured 3.0 V motor supply and driver from
the wiring guide. Bench modes are component tests, not navigation operation.
Recompile without STRIDE_SELF_TEST (default 0) for normal local sensing/network.
Native tests verify pulse timing and no replay after completion or delayed start.
