# Agent 3 vision integration

The current integration contract and exact Agent 1 requests are in
[handoff/vision-hardware.md](../../handoff/vision-hardware.md).

This module now follows `contracts/API.md` at main `85d445f`: canonical normalized
XYXY `box`, a `VisionService(settings)` lifecycle, `offer_frame`, `invalidate`,
async candidate callback and exported `router`. It never publishes final speech
or its own global state sequence. Earlier 0..1000 `box_2d`, `submit`, and router
factory instructions are superseded. No frontend/backend application was added.
