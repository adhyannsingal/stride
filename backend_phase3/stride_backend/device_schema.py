"""Additive device component migration; base route schema remains version 1."""

DEVICE_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (component TEXT PRIMARY KEY, version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS devices (
 device_id TEXT PRIMARY KEY, session_id TEXT UNIQUE, registered_at INTEGER NOT NULL,
 paired_at INTEGER, last_event_key TEXT, last_command_id TEXT
);
CREATE TABLE IF NOT EXISTS device_boots (
 device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
 boot_id TEXT NOT NULL, retired INTEGER NOT NULL CHECK(retired IN (0,1)),
 first_received_ms INTEGER NOT NULL, PRIMARY KEY(device_id,boot_id)
);
CREATE TABLE IF NOT EXISTS device_state (
 device_id TEXT PRIMARY KEY REFERENCES devices(device_id) ON DELETE CASCADE,
 boot_id TEXT, sequence INTEGER, uptime_ms INTEGER, payload_hash TEXT,
 received_ms INTEGER, received_mono INTEGER, runtime_id TEXT,
 contact_ms INTEGER, contact_mono INTEGER, contact_runtime TEXT,
 distance_cm REAL, sensor_valid INTEGER NOT NULL DEFAULT 0,
 measurement_reason TEXT, obstacle_state TEXT NOT NULL DEFAULT 'unknown', clear_count INTEGER NOT NULL DEFAULT 0,
 last_valid_distance_cm REAL, last_valid_ms INTEGER, last_valid_mono INTEGER, last_valid_runtime TEXT,
 battery_percent REAL, firmware_version TEXT, source TEXT
);
CREATE TABLE IF NOT EXISTS device_telemetry (
 row_id INTEGER PRIMARY KEY AUTOINCREMENT,
 device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
 boot_id TEXT NOT NULL, sequence INTEGER NOT NULL, uptime_ms INTEGER NOT NULL,
 received_ms INTEGER NOT NULL, distance_cm REAL, measurement_valid INTEGER NOT NULL,
 sensor_valid INTEGER NOT NULL, measurement_reason TEXT, source TEXT NOT NULL,
 battery_percent REAL, sensor_status TEXT, firmware_version TEXT, diagnostics_json TEXT NOT NULL,
 UNIQUE(device_id,boot_id,sequence)
);
CREATE TABLE IF NOT EXISTS haptic_commands (
 command_id TEXT PRIMARY KEY, device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
 session_id TEXT NOT NULL, boot_id TEXT NOT NULL,
 navigation_id TEXT REFERENCES navigation_sessions(navigation_id), state_revision INTEGER NOT NULL,
 event_key TEXT NOT NULL, guidance_event_id TEXT REFERENCES guidance_events(event_id),
 kind TEXT NOT NULL CHECK(kind IN ('left','right','straight','stop','cancel')), priority INTEGER NOT NULL,
 created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, expires_mono INTEGER NOT NULL,
 runtime_id TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('issued','delivered','received','executed','rejected','expired','canceled')),
 delivered_at INTEGER, UNIQUE(device_id,event_key)
);
CREATE TABLE IF NOT EXISTS haptic_acknowledgments (
 command_id TEXT NOT NULL REFERENCES haptic_commands(command_id) ON DELETE CASCADE,
 status TEXT NOT NULL CHECK(status IN ('received','executed','rejected','expired')),
 received_at INTEGER NOT NULL, PRIMARY KEY(command_id,status)
);
CREATE INDEX IF NOT EXISTS telemetry_device_history ON device_telemetry(device_id,row_id);
CREATE INDEX IF NOT EXISTS haptic_device_status ON haptic_commands(device_id,status,priority);
"""
