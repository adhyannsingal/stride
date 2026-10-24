---
inclusion: always
---
# Product

STRIDE is a navigation-assistance prototype for blind and low-vision users, developed at Hackachusetts 2026. It complements established mobility aids with checked-route guidance, camera awareness, historical sightings and obstacle feedback.

The wearable architecture uses a W11 ESP32 Cam ESP32-S3 module with OV3660 camera Sense Kit. A separate ESP32 DevKit V1 receives HC-SR04 range measurements and controls local alerts and motor patterns. The web dashboard is designed for phone and desktop; browser speech uses the user's selected audio output. Mac webcam capture supports development.

Core user controls: connect a session, grant upload consent, start awareness, choose a checked route, explicitly confirm checkpoints, repeat, pause/resume and stop. Memory distinguishes last-seen observations from the current scene. Large controls, text sizes, keyboard access and appearance options matter more than decorative dashboard content.

Preserve the approved landing page and animation. Never present a simulated input as a physical measurement. Never infer metric distance or safe walking directions from bounding boxes. Do not introduce automatic localization or rerouting. Camera consent must precede capture/upload; stop and revocation must release browser tracks. A browser test or firmware ACK does not establish physical safety or perceived vibration.
