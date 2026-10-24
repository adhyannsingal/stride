---
inclusion: always
---
# Technology and contracts

- Frontend: React, TypeScript and Vite under frontend/. Browser-camera fallback requires consent; browser speech uses SpeechSynthesis and cannot prove the chosen AirPods output.
- Backend: one-process FastAPI app under backend_phase3/stride_backend/, Pydantic schemas, SQLite route/memory/device state and an in-memory latest-frame/inference controller. Run one Uvicorn worker unless state sharing is redesigned.
- Vision: app/vision/ provides a YOLOv8n ONNX Runtime detector adapter. The backend detector protocol and STRIDE_DETECTOR_FACTORY remain the integration seam. Do not make fixture output look real.
- Hardware: firmware/ has separate W11 camera and ESP32 feedback-controller code. Immediate ultrasonic warning remains local even if HTTP, Wi-Fi, the phone or inference fails.

Use the current code and OpenAPI for exact fields. Core APIs include /auth/session, /frame, /vision, /vision/latest, /routes, /route, /memory, /telemetry, /device/pair, /device/status and device command polling/ACK. UI session credentials, camera token and controller tokens are distinct. Keep secrets in environment variables. Route mutations use action IDs, navigation IDs and expected revisions; retries after uncertain delivery reuse the exact original action ID and payload.

Use backend_phase3/README.md, backend_phase3/DEVICE_INTEGRATION.md, app/vision/ and frontend/src/app/api.ts as current contract references. Report tests and physical checks separately.
