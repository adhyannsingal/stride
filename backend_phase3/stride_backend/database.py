"""Short SQLite transactions, one connection per operation; no ORM or secrets."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3

from starlette.concurrency import run_in_threadpool

from .errors import BackendError

SCHEMA = """
CREATE TABLE IF NOT EXISTS routes (
    route_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
    checked INTEGER NOT NULL CHECK (checked IN (0,1)),
    demo_fixture INTEGER NOT NULL CHECK (demo_fixture IN (0,1)), verification_note TEXT
);
CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY, route_id TEXT NOT NULL REFERENCES routes(route_id),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0), instruction TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('left','right','straight','stop')),
    landmark TEXT, return_instruction TEXT, return_direction TEXT,
    return_checked INTEGER NOT NULL DEFAULT 0 CHECK (return_checked IN (0,1)),
    UNIQUE(route_id, ordinal)
);
CREATE TABLE IF NOT EXISTS navigation_sessions (
    navigation_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
    route_id TEXT NOT NULL REFERENCES routes(route_id),
    state TEXT NOT NULL CHECK (state IN ('idle','guiding','paused','blocked','completed')),
    current_index INTEGER NOT NULL CHECK (current_index >= 0),
    confirmed_count INTEGER NOT NULL CHECK (confirmed_count >= 0),
    revision INTEGER NOT NULL CHECK (revision >= 0),
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS navigation_heads (
    session_id TEXT PRIMARY KEY, navigation_id TEXT NOT NULL REFERENCES navigation_sessions(navigation_id),
    revision INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS route_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
    navigation_id TEXT NOT NULL REFERENCES navigation_sessions(navigation_id),
    action TEXT NOT NULL, prior_state TEXT NOT NULL, resulting_state TEXT NOT NULL,
    checkpoint_index INTEGER NOT NULL, timestamp INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS route_actions (
    session_id TEXT NOT NULL, action_id TEXT NOT NULL, request_json TEXT NOT NULL,
    navigation_id TEXT REFERENCES navigation_sessions(navigation_id), applied_revision INTEGER NOT NULL,
    error_status INTEGER, error_code TEXT, error_message TEXT,
    PRIMARY KEY(session_id, action_id)
);
CREATE TABLE IF NOT EXISTS guidance_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
    navigation_id TEXT NOT NULL REFERENCES navigation_sessions(navigation_id),
    session_id TEXT NOT NULL, instruction TEXT NOT NULL, direction TEXT NOT NULL,
    created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, state_revision INTEGER NOT NULL,
    checkpoint_id TEXT NOT NULL REFERENCES checkpoints(checkpoint_id),
    valid INTEGER NOT NULL CHECK (valid IN (0,1))
);
CREATE TABLE IF NOT EXISTS object_sightings (
    sighting_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, label TEXT NOT NULL,
    checkpoint_id TEXT REFERENCES checkpoints(checkpoint_id), frame_id TEXT NOT NULL,
    receipt_id TEXT NOT NULL, device_id TEXT NOT NULL, boot_id TEXT NOT NULL,
    source_revision INTEGER NOT NULL, vision_generation INTEGER NOT NULL, vision_instance_id TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('real','simulated','fixture')),
    provider TEXT NOT NULL CHECK (provider IN ('yolo','gemini','fixture')),
    captured_at INTEGER, captured_ms INTEGER NOT NULL, received_at INTEGER NOT NULL,
    recorded_at INTEGER NOT NULL, last_seen_at INTEGER NOT NULL,
    timestamp_basis TEXT NOT NULL CHECK (timestamp_basis IN ('server_receipt','aligned_capture')),
    track_id TEXT NOT NULL,
    UNIQUE(session_id, device_id, boot_id, source_revision, vision_generation, vision_instance_id, track_id, label, source, provider)
);
CREATE INDEX IF NOT EXISTS navigation_session_history ON navigation_sessions(session_id, created_at);
CREATE INDEX IF NOT EXISTS route_event_history ON route_events(navigation_id, seq);
CREATE INDEX IF NOT EXISTS guidance_current ON guidance_events(navigation_id, valid, seq);
CREATE INDEX IF NOT EXISTS sightings_session_age ON object_sightings(session_id, last_seen_at);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(path) == ":memory:":
            raise ValueError("Use a temporary SQLite file; per-operation connections require a file database")

    @contextmanager
    def transaction(self, *, write=False):
        connection = sqlite3.connect(str(self.path), timeout=2, isolation_level=None)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction(write=True) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError("Unsupported STRIDE SQLite schema version")
            # Execute static statements individually: executescript implicitly
            # commits, which would break atomic initialization.
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    connection.execute(statement)
            connection.execute("PRAGMA user_version=1")

    async def run(self, function, *args, **kwargs):
        try:
            return await run_in_threadpool(function, *args, **kwargs)
        except sqlite3.Error:
            raise BackendError(503, "database_unavailable", "Route memory is temporarily unavailable") from None
