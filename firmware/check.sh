#!/bin/sh
set -eu
cli=${ARDUINO_CLI:-arduino-cli}
artifact_dir=${STRIDE_FIRMWARE_BUILD_DIR:-/tmp/stride-firmware-check}
mkdir -p "$artifact_dir"
"$cli" compile --fqbn esp32:esp32:esp32 --build-path "$artifact_dir/feedback" firmware/feedback > "$artifact_dir/feedback.log" 2>&1
"$cli" compile --fqbn esp32:esp32:esp32s3 --build-property 'compiler.cpp.extra_flags=-DSTRIDE_CAMERA_COMPILE_ONLY' --build-path "$artifact_dir/camera-syntax" firmware/camera > "$artifact_dir/camera-syntax.log" 2>&1
# Negative check only applies when the human has not supplied board_config.h.
if [ ! -f firmware/camera/board_config.h ]; then
  if "$cli" compile --fqbn esp32:esp32:esp32s3 --build-path "$artifact_dir/camera-gate" firmware/camera > "$artifact_dir/camera-gate.log" 2>&1; then
    echo 'FAIL: unconfigured W11 unexpectedly compiled'; exit 1
  fi
  rg -q 'W11 blocked: verify PCB revision' "$artifact_dir/camera-gate.log"
fi
cat "$artifact_dir/feedback.log" "$artifact_dir/camera-syntax.log"
echo 'PASS: feedback compile, camera syntax compile and unconfigured-board gate; no flash or physical validation'
