---
inclusion: always
---
# STRIDE product

STRIDE is a supervised navigation-assistance prototype for blind and low-vision users. It combines current camera object awareness, manually checked route instructions, historical last-seen memory and ultrasonic proximity alerts. The web app presents state and speaks through the browser's selected audio output; ESP32 local alerts must operate independently of the backend.

Keep observed facts distinct: a YOLO box is an image-relative position, not metric distance or a safe path; a recalled object is last seen, not currently visible; a user-confirmed checkpoint is route progress, not automatic localization. Never turn an unchecked demo route into walking guidance. Unknown or stale sensor readings are not clear. Do not imply that command delivery proves vibration or that software tests prove physical safety.

Current gaps include hosted W11-to-phone integration, physical sensor/motor calibration, actual iPhone/AirPods audibility and server-authorized speech arbitration. Read the root README and backend device guide for the current status before making claims.
