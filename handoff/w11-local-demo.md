# Meshnology W11 — camera-only local demo

The user's exact ASIN is B0GTQMX5HB, listed as Meshnology W11 with OV3660. Its official W11 documentation specifies the XIAO_ESP32S3 Arduino target. Vendor source/schematic, not the partial FCC ID, establishes this software profile. Physical board, camera sensor/revision, orientation and actual operation still require validation.

Sources:
- https://www.amazon.com/dp/B0GTQMX5HB
- https://wiki.meshnology.com/W11/W11_ESP32S3_Mini_Module/
- Vendor downloadable example: W11demo_16-20, 16_Video_stream_face_recognition/camera_pins.h, CAMERA_MODEL_XIAO_ESP32S3
- Expansion schematic: https://wiki.meshnology.com/assets/files/W11Expansion%20board-979f7fe28cdd0abfe6956514b8bc459f.pdf

## What is prepared

`scripts/prepare_w11_demo.py` uses the installed Espressif Arduino CameraWebServer example and checks its XIAO pin map against the vendor W11 profile. It disables auxiliary LED use and releases shared GPIO48, selects VGA capture, reads private WiFi settings from a file outside Git, and adds a camera-monotonic frame-age header to `/capture`. No face-recognition libraries, SD card or hosted uploader is used in this example. It is a separate camera-only bring-up path, not a fix to the hosted uploader's API mismatch.

Documented pins: D0–D7 = 15,17,18,16,14,12,11,48; XCLK=10; SDA=40; SCL=39; VSYNC=38; HREF=47; PCLK=13; PWDN/RESET=-1. These are internal camera signals: do not hand-wire them to the separate DevKit. Keep the kit's mainboard/expansion board/ribbon assembled correctly, with power disconnected during assembly. No RGB/SD peripheral is started.

## 1. Identify ports before flashing

At the latest check only `/dev/cu.usbserial-0001` appeared. USB registry identifies CP2102 and esptool recognizes ESP32, consistent with the DevKit, although the chip read ends early. No second USB device/native ESP32-S3 serial port is detected. This is not evidence that the W11 is ready to flash. Check a known USB data cable/direct port; use a labeled BOOT button while connecting if necessary. Do not install arbitrary USB drivers or guess a port.

Keep the two targets separate: DevKit uses esp32:esp32:esp32; vendor W11 uses esp32:esp32:XIAO_ESP32S3 with OPI PSRAM. Only flash the positively identified matching board. USB LED indicates power only.

## 2. Configure WiFi and compile

Prepared on this machine:

```sh
cd /Users/adhyannsingal/Documents/Codex/2026-10-22/referenced-chatgpt-conversation-this-is-an/stride
/tmp/stride-phase2-venv/bin/python scripts/prepare_w11_demo.py
```

Edit only the SSID/password values in `/tmp/stride-w11-camera/CameraWebServer/secrets.h`. Use a private 2.4 GHz-capable demo network reachable by the Mac; venue guest isolation can block the Mac-to-camera connection. Keep credentials private. The camera serves images on the LAN. Re-running preparation preserves the private credentials file.

```sh
/tmp/stride-arduino/arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3:PSRAM=opi --build-path /tmp/stride-w11-camera-build /tmp/stride-w11-camera/CameraWebServer
```

This exact target compiled with Arduino-ESP32 3.3.2 after the frame-age header change: 1,002,487 bytes program, 66,720 bytes globals. Compile only; not flashed/physically tested. Compile again after editing WiFi values. It uses the board target's default partition settings; don't independently force another model/PSRAM mode or flash offset.

Once W11's actual matching USB port is identified:

```sh
/tmp/stride-arduino/arduino-cli upload --fqbn esp32:esp32:XIAO_ESP32S3:PSRAM=opi --port ACTUAL_W11_USB_PORT --input-dir /tmp/stride-w11-camera-build /tmp/stride-w11-camera/CameraWebServer
/tmp/stride-arduino/arduino-cli monitor --port ACTUAL_W11_USB_PORT --config baudrate=115200
```

Look for camera initialization and `Camera Ready! Use http://...`. Use the actual printed IP. If initialization fails, preserve the code/error and inspect the supplied ribbon/expansion/PSRAM/board match; do not try random GPIO maps. If USB monitor appears silent, re-enumerate its port after boot and use the board's reset button. No success is claimed until real frames appear.

## 3. Real camera images into existing Mac YOLO/audio

Close the laptop webcam preview. After the camera-only web page works, run from the repository:

```sh
./Start_Stride_Demo.command --camera-url http://ACTUAL_CAMERA_LAN_IP/capture
```

This continuously pulls fresh JPEG frames automatically, runs the existing local YOLO, and sends the preview's optional object-awareness speech through selected Mac audio/AirPods. There is no repeated Analyze click and no hosted backend requirement in this development demo.

The adapter retains no video queue, limits JPEGs and request time, disables redirects, and accepts only an explicit numeric local-camera address. With the prepared firmware, it uses camera-reported frame age plus conservative request timing; stale frames cannot produce current-scene speech. An unmodified camera example without the new header can display diagnostic images but object speech is disabled. Header validation is a local diagnostic check, not authenticated hosted clock verification or a validated safety latency guarantee. Keep boxes/orientation/actual rate and misses under observation.

This is a **W11 → local Mac YOLO → Mac/AirPods development demo**. It is not the laptop-independent hosted/iPhone runtime. Final deployment and sensor/route speech arbitration remain separate. No automatic avoidance direction is inferred from boxes.

## Software evidence

53 vision/integration tests passed, 2 optional fixture tests skipped. Added HTTP-source tests cover valid JPEG/BGR decoding, nonlocal/credential URL rejection, missing age → visual only, stale/invalid age rejection, release and HTML rejection. The real camera build compiles. No W11 flash, WiFi exchange, camera image, range measurement or physical system integration is claimed by these checks.
