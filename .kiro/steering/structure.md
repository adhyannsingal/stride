---
inclusion: always
---
# Repository structure and work boundaries

- README.md: current architecture, quick start, evidence and limitations.
- backend_phase1/ and backend_phase2/: historical milestones. Add new backend work only to backend_phase3/ unless the team explicitly changes the canonical app.
- backend_phase3/stride_backend/: active FastAPI app. Its tests are in backend_phase3/tests/.
- app/vision/: YOLO adapter, tracking and model support; tests/vision/ and tests/integration/ cover related behavior.
- frontend/src/app/: React application, API adapter, controllers and policy. frontend/tests/ holds frontend contract and browser checks.
- firmware/: W11 camera and separate ESP32 feedback firmware. docs/ contains hardware and local-demo procedures.
- qa/: recorded software and demo evidence. Historical test reports are not fresh results.
- .kiro/steering/: current workspace guidance for future Kiro sessions; Kiro_Usage.md explains evidence and attribution.

Inspect Git status and applicable owner docs before editing. Preserve teammate changes. Treat route safety, sensor freshness, speech priority and source identity as separate concerns. Do not silently copy features into historical phase folders or claim a component has been physically tested because it compiles.
