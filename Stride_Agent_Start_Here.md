# Stride — choose your coding-agent brief

The current three-agent split replaces the previous single-agent kickoff and all older numbering:

- [Agent 1 — Backend](Agent_1_Backend.md): shared contracts, FastAPI, routes/memory, server device policy and deployment.
- [Agent 2 — Frontend](Agent_2_Frontend.md): phone UI, browser capture and AirPods speech playback.
- [Agent 3 — Hardware and vision — Adhyann](Agent_3_Hardware_Vision.md): model, inference service, firmware, hardware and integration evidence.

Give each agent its own brief and access to the same repository. Read [the shared API contract](contracts/API.md) before coding. Agent 1 is the sole writer of shared app/schema/settings/dependency files. The integration plan, merge order and acceptance gates are in Agent 3's brief. No old role allocation should override these files.

See [team build spec](buildspec_stride.md), [live requirements](Stride_Live_Vision_Requirements.md) and [wiring guide](Stride_Hardware_Wiring_Guide.md). Work with real webcam images and explicitly simulated sensors now; physical assembly is the final integration stage. Current docs do not prove implementation or hardware operation.
