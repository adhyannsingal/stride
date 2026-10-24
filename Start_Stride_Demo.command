#!/bin/bash
# Finder/Terminal launcher. Resolve this checkout rather than the caller's cwd.
set -u
stride_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
cd "$stride_root" || exit 1

stride_finish() {
    stride_exit=$?
    if [ "$stride_exit" -ne 0 ]; then
        echo "Stride did not start or exited with an error (code $stride_exit). Read the error above."
    fi
    if [ -t 0 ] && [ -t 1 ]; then
        read -r -p "Press Return to close this launcher... " stride_reply
    fi
}
trap stride_finish EXIT

stride_python="${STRIDE_PYTHON:-}"
if [ -z "$stride_python" ]; then
    for stride_candidate in "$stride_root/.venv-phase3/bin/python" "$stride_root/.venv-phase2/bin/python" "$stride_root/.venv/bin/python" /tmp/stride-phase2-venv/bin/python; do
        if [ -x "$stride_candidate" ]; then
            stride_python="$stride_candidate"
            break
        fi
    done
fi
if [ -z "$stride_python" ] || [ ! -x "$stride_python" ]; then
    echo "No prepared Python environment found. Follow README model/dependency setup, or set STRIDE_PYTHON to your environment's Python."
    exit 1
fi
if ! "$stride_python" -c 'import cv2, numpy, onnxruntime, PIL'; then
    echo "The selected environment is missing preview dependencies. Follow README setup."
    exit 1
fi
if [ ! -f "$stride_root/models/yolov8n.onnx" ]; then
    echo "Model missing: models/yolov8n.onnx. Follow handoff/backend-vision-integration.md model export/setup."
    exit 1
fi
echo "Stride local object-awareness demo"
echo "Folder: $stride_root"
echo "Select AirPods as Mac output. Close other camera apps. P pauses; Q/Esc quits."
export PYTHONPATH="$stride_root"
"$stride_python" -u "$stride_root/scripts/preview_live.py" --speak "$@"
