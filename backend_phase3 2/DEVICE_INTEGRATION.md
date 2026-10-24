# STRIDE Phase 4 — controller and frontend handoff

The Phase 4 application remains in **backend_phase3/**. One FastAPI process and
one Uvicorn worker/replica are required. These APIs are supplemental monitoring
and optional route cues. No ESP32, electrical circuit, local alarm, motor, Wi-Fi
link or wearer perception has been physically verified by the backend tests.

**Firmware must run its immediate local obstacle-warning loop independently.**
Never wait for HTTP, the phone, YOLO or the backend before issuing a local warning.
A remote `cancel` cancels remote route patterns only; it must never disable or
silence the device's local warning loop. The firmware/hardware owner implements
and validates the protected drivers. The backend sends no GPIO or wiring commands.

## 1. Provision and explicitly pair

The camera and ultrasonic/haptic controller may be separate boards. Give each
physical controller a stable ID and its own secret. Do not reuse the camera or
UI secret. Configure server environment variables (values below are placeholders):

```dotenv
STRIDE_DEVICE_TOKEN=<separate-camera-secret>
STRIDE_SESSION_TOKENS={"demo-1":"<ui-session-secret>"}
STRIDE_CONTROLLER_TOKENS={"esp32-ultrasonic-01":"<controller-secret>"}
STRIDE_CONTROLLER_SESSIONS={"esp32-ultrasonic-01":"demo-1"}
```

Use random provisioned secrets and keep real values outside Git and frontend
builds. `STRIDE_CONTROLLER_SESSIONS` is an operator-approved allowlist, not a
client-selected session ID. One controller per UI session is supported. The
backend registers IDs at startup, but they remain **unpaired** until the authorized
frontend/backend owner performs this request:

```sh
curl "$STRIDE_URL/device/pair" \
  -H "X-Session-Token: $STRIDE_UI_SECRET" \
  -H 'Content-Type: application/json' \
  --data '{"device_id":"esp32-ultrasonic-01","session_id":"demo-1"}'
```

`STRIDE_URL` is your local URL or deployed HTTPS origin; no hostname is hardcoded.
For example, local development uses `http://127.0.0.1:8000`.
Response: `{"device_id":"esp32-ultrasonic-01","session_id":"demo-1","paired":true,"duplicate":false}`.
Repeating pairing returns `duplicate=true`. Another UI session cannot attach the
controller. Firmware needs only its controller secret, not the UI/camera secrets.

Browsers can use the existing `POST /auth/session` exchange and HttpOnly cookie
instead of the script's `X-Session-Token`; use `credentials: "include"`. A browser
cookie never authorizes telemetry, command polling or device acknowledgments.
It grants access only to its own allowed device's status/pairing.

For explicitly local tokenless tests only, set `STRIDE_LOCAL_DEV=true`, leave
controller tokens empty, retain the allowed-session mapping, and send
`X-Device-ID: <provisioned-id>` on controller calls. No arbitrary ID is accepted.
Production requires device-specific secrets; it never falls back to UI or camera
authentication. Empty controller configuration leaves the existing app usable,
but controller authentication endpoints report 503 until provisioned.

## 2. Telemetry

Canonical: **POST /telemetry**. Alias: `POST /device/telemetry`.
Always send `X-Device-Token: <controller-secret>` in production. The credential
identifies the controller before the body is read; body `device_id` must match.
Do not include `session_id`; association comes from pairing, not telemetry.

```sh
curl "$STRIDE_URL/telemetry" \
  -H "X-Device-Token: $STRIDE_CONTROLLER_SECRET" \
  -H 'Content-Type: application/json' \
  --data '{"device_id":"esp32-ultrasonic-01","boot_id":"boot-123","sequence":42,"uptime_ms":80520,"distance_cm":37.5,"measurement_valid":true,"battery_percent":null,"source":"real"}'
```

Required: `device_id`, a new unique `boot_id` per device reboot, integer `sequence`,
integer `uptime_ms`, and boolean `measurement_valid`. Counters are nonnegative signed 64-bit integers. Distance is centimeters;
use null for invalid/no-echo readings. An absent/null distance is unknown even if
measurement_valid was incorrectly declared true. Optional battery is 0–100 only
when actually measured. Optional `firmware_version`/`sensor_status` are at most
64 characters. Omitted battery/firmware values remain null, never invented.

Optional diagnostic metadata has at most eight keys (64 characters each), scalar
values, and a 1,024-byte JSON cap. Never include credentials or personal/location
information in diagnostics. Entire JSON bodies are limited to 4,096 bytes by
default, including streamed requests. Numeric distances/battery must be finite;
negative/NaN/infinity values return 422. Malformed JSON returns the normal 422
validation envelope. Oversized JSON returns 413, wrong media type 415.

The legacy field `valid` is accepted as an alias for `measurement_valid`.
`source=real` is the physical-controller default. `fixture`/`simulated` are allowed
only in explicitly local development/tests and remain labeled as such.

A response contains exactly these typed fields (example):

```json
{
  "device_id": "esp32-ultrasonic-01",
  "accepted": true,
  "duplicate": false,
  "received_ms": 1700000001000,
  "obstacle_state": "danger",
  "telemetry_fresh": true,
  "sensor_valid": true,
  "measurement_reason": null,
  "navigation_state": null,
  "navigation_revision": null,
  "physical_alert_verified": false
}
```

HTTP 200 confirms backend processing, not that a buzzer or vibration occurred.
The sample timestamp/state is illustrative; navigation fields reflect the actual
associated route. Start at **5 Hz**, optionally 5–10 Hz after supervised testing.
`STRIDE_CONTROLLER_EXPECTED_HZ` publishes the expected rate in status; it is not
a claim that this rate was measured on hardware.

Sequence must strictly increase within a boot; uptime must not regress. An exact
retry of the latest sequence is idempotent but never refreshes receipt/freshness.
An older sequence, conflicting duplicate, decreasing uptime, or a retired boot
returns 409. A new unseen boot ID permits a reboot; known old boot packets can
never become current. Sequence history survives server restart. Boot tombstones
are bounded (16 per controller by default); at capacity new boots return 429
until the operator increases the configured bound or reviews reprovisioning.
Unseen boot ordering cannot be inferred from arbitrary boot IDs: firmware must
always generate new IDs and discard queued packets from earlier boots.

Keep only the newest reading for network transmission. Do not replay an offline
measurement backlog. Server receipt time is authoritative for freshness; uptime
is not synchronized UTC and does not prove actual sample-to-server latency.
After reconnect, send a new current measurement with an increased sequence.
Local warnings continue during every failure/reconnect/401/409/429/503 condition.

## 3. Classification, freshness and route holds

Configurable demonstration defaults:

| Classification | Effective fresh valid reading |
| --- | --- |
| danger | <=50 cm, immediate; no averaging/debounce delays entry |
| caution | >50 and <=100 cm |
| clear | >100 cm and within the supported range |
| unknown | Invalid, absent, unsupported, timed out, or stale |

Supported software range defaults to 2–400 cm. Out-of-range values are accepted
for diagnostics but classified unknown, never infinite clear space. Any sensor
status other than omitted/`ok`/`valid` makes the measurement unknown. Original
values are retained. Hysteresis holds danger through 55 cm and caution through
105 cm when recovering from those states. These are software engineering defaults,
not validated mobility-safety limits. They override older suggested backend bands;
the firmware owner must separately calibrate the independent local alarm policy.

A measurement expires after **1,000 ms** using monotonic server time. Communication
availability uses a separate **2,000 ms** contact window. New accepted telemetry,
authenticated command polls and successful ACKs establish communication; they do
not renew a measurement. Invalid fresh telemetry can mean connected + unknown.
Frontend status polling renews neither. Duplicate telemetry renews neither.

Once a controller is paired, danger, caution, unknown, stale data, and reboot hold
active/paused navigation in blocked state and invalidate ordinary cues. Recovery
requires **three consecutive fresh valid readings >105 cm**, without a stale gap.
Recovery changes blocked to paused; a human must explicitly resume. No distance
change confirms a checkpoint or establishes the user's position. A fixed monitor
(default 100 ms) enforces timeouts, and route/control/status requests also check
inside the same SQLite transaction. Concurrent confirm and danger updates are
serialized; they cannot leave a valid turn cue after the danger update commits.

Without a paired controller, Phase 3's checked-route demo behavior remains,
explicitly labeled `sensor_monitoring=not_associated`. A configured but unpaired
controller does not count as protection. Route responses add optional
`sensor_monitoring`, `paired_device_id`, and `obstacle_state` fields. Vision state
and navigation history remain independent.

## 4. Poll optional haptic commands

Canonical: **GET /devices/{device_id}/commands**.
Alias: `GET /device/commands?device_id=...`.

```sh
curl "$STRIDE_URL/devices/esp32-ultrasonic-01/commands" \
  -H "X-Device-Token: $STRIDE_CONTROLLER_SECRET"
```

The old unimplemented planning sketch showed a list. This implementation defines
one typed, one-shot envelope; no previous working endpoint used that list shape:

```json
{
  "device_id": "esp32-ultrasonic-01",
  "server_ms": 1700000001000,
  "command": {
    "command_id": "bb8ce5fa-bc85-4848-8236-cc1b5c136d2c",
    "device_id": "esp32-ultrasonic-01",
    "session_id": "demo-1",
    "boot_id": "boot-123",
    "navigation_id": "89f272c1-2001-449d-b3ab-000ede0d9b55",
    "state_revision": 1,
    "kind": "straight",
    "priority": 10,
    "created_at": 1700000001000,
    "expires_at": 1700000002000,
    "remaining_ttl_ms": 1000,
    "status": "delivered",
    "execution_reported": false,
    "perception_verified": false
  }
}
```

This straight-cue example was generated in an isolated synthetic test after three
clear samples and an explicitly checked test route. The earlier danger payload
would instead hold navigation and may produce a priority stop/cancel. IDs and
clock values vary; commands come only from current application events. Polling
does not fabricate a new route instruction.

Empty response is `{"device_id":"...","server_ms":1700000001000,"command":null}`.
Commands are returned once, marked delivered atomically before response. This
means returned by the server, not confirmed received by hardware. Repeated polling
will not return that cue again; a lost response drops the optional cue. Poll at
roughly 5–10 Hz. Keep a bounded firmware deduplication set of command IDs.

Ordinary cues have a default **1,000 ms** TTL, configurable up to **1,500 ms**.
Before executing: verify device/boot identity, reject seen IDs, subtract the full
poll round-trip duration from remaining_ttl_ms, then use local monotonic time to
count down the remainder. Do not compare expires_at with unsynchronized uptime.
Never start/continue a cue beyond its remaining TTL. Check local sensor priority
before any optional remote pattern. Do not queue old remote patterns for replay.

Priorities: normal left/right/straight=10, checked-route stop=80, cancel=90,
supplemental danger stop=100. Stop/cancel supersede lower-priority pending,
delivered or received cues. A danger stop stays latched while blocked even when
telemetry becomes unknown; it is not downgraded by loss of sensor data and is not
reissued after its TTL. Fresh recovery or explicit route stop changes the cue.
Pause/stop/completion/block/controller boot/revision
changes invalidate old commands. A delivered cue cannot be remotely unsent;
short TTL, frequent polling and local firmware interruption bound that behavior.
No backend cancellation proves a motor actually stopped.

## 5. Acknowledgments

**POST /device/ack** or **POST /devices/{device_id}/ack**:

```sh
curl "$STRIDE_URL/device/ack" \
  -H "X-Device-Token: $STRIDE_CONTROLLER_SECRET" \
  -H 'Content-Type: application/json' \
  --data '{"device_id":"esp32-ultrasonic-01","command_id":"bb8ce5fa-bc85-4848-8236-cc1b5c136d2c","status":"received"}'
```

Lifecycle: issued → delivered (one poll) → received (ACK) → executed/rejected/expired.
A delivered command may also be rejected/expired directly. ACK received before
execution, then recheck TTL/local priority. Only explicitly reported execution is
recorded as executed, within the current command validity window. If rejected or
expired, discard it. Legacy ACK names accepted/completed map to received/executed.

Response example:
`{"device_id":"esp32-ultrasonic-01","command_id":"bb8ce5fa-bc85-4848-8236-cc1b5c136d2c","acknowledged":true,"duplicate":false,"status":"received","execution_reported":false,"perception_verified":false}`.
Identical ACK retries are idempotent (200, duplicate=true), unlike the old planning
sketch's duplicate 409. Impossible transitions and obsolete boot/navigation
revisions return 409; unknown/pruned IDs return 404; cross-device ACKs return 403.
A duplicate old ACK never makes an expired/canceled command valid again.
`execution_reported=true` means a firmware assertion, not verified movement or
proof that the wearer perceived a cue.

## 6. Device status and frontend display

```sh
# Firmware/controller authorization:
curl "$STRIDE_URL/device/status?device_id=esp32-ultrasonic-01" \
  -H "X-Device-Token: $STRIDE_CONTROLLER_SECRET"
# Authorized frontend session (cookie can replace this header):
curl "$STRIDE_URL/device/status?device_id=esp32-ultrasonic-01" \
  -H "X-Session-Token: $STRIDE_UI_SECRET"
```

Responses use no-store. `device_models.py` and Swagger define the complete schema.
Display these distinctions:

- availability unknown: no authenticated contact yet; connected: recent telemetry/
  polling/ACK contact; stale: contact expired. Unauthorized requests return 401/403
  and cannot update health. Registration alone never means connected.
- telemetry_fresh: recent accepted packet; measurement_fresh/sensor_valid: usable
  recent measurement. An invalid packet can keep communication connected while
  obstacle_state stays unknown.
- current_distance_cm is null when invalid/stale. last_valid_distance_cm and
  last_valid_distance_age_ms are historical diagnostics. Prefer “Sensor last
  reported 42 cm, <age> ago”; do not present an old number as current physical range.
- Show source=fixture/simulated explicitly in local tests. Battery and firmware
  appear only as actually reported. local_alerts_verified is always false here.
- navigation_state/revision expose holds. Pending commands include issued,
  delivered and received states. latest_command and last_acknowledged_command_id
  distinguish server delivery, ACK and reported execution. None prove perception.
  Status.latest_command is audit information, never an execution queue.

The existing `/status` response is unchanged. Browser cookies never grant access
to another session's controller. No device credentials are returned in status.

## 7. Persistence, restart and remaining checks

The additive devices component migration creates devices, device_boots,
device_state, bounded device_telemetry, haptic_commands and haptic_acknowledgments.
Base SQLite user_version remains 1 for Phase 3 compatibility; component version 1
is recorded in schema_migrations. Existing route/memory tables are retained.
Foreign keys and parameterized transactions cover sequence acceptance, route
holds, supersession and ACK transitions. No credentials or images are stored.

Defaults: eight registered controllers, 100 telemetry rows/controller, 16 boot
IDs/controller and 64 commands/controller. Pruning commands cascades their bounded
ACK audit. Sensor-generated route transitions are separately capped at 128 per
navigation; human confirmations and route actions are retained. A last-event marker prevents current cues from being recreated merely
because terminal command history was pruned. Old boot tombstones are not silently
evicted. Operator mapping changes require new authorized pairing.

Restart cancels prior active commands and invalidates telemetry/contact freshness,
while preserving boot/sequence checks, route progress and historical readings.
Send fresh telemetry before command polling after a device reboot. Do not reuse
old boot IDs, sequences, command IDs or queued patterns. A server restart never
refreshes an old persisted measurement or resumes route guidance automatically.

Real ESP32 exchange, firmware TTL/dedup/local-priority behavior, power-loss and
Wi-Fi-loss behavior, actual driver/motor operation, mounting/range calibration,
alert latency and wearer perception still require supervised physical tests.
No electrical instructions or firmware implementation are supplied here.
