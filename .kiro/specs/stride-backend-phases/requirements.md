# STRIDE backend phases — retrospective requirements

Prepared from existing source on 2026-10-24. This is a consolidated reference for continued work, not a claim these documents were generated through Kiro's native spec workflow before implementation.

## Phase 1: ingestion foundation

- The service shall expose health, server time, OpenAPI and authenticated multipart JPEG ingestion without requiring a model.
- It shall decode JPEGs, validate identifiers, sequence numbers, source metadata, normalized detection boxes and numeric bounds, and return a consistent JSON error envelope.
- It shall authenticate before reading upload bodies, bound request bytes and decoded pixels, and avoid image persistence/logging by default.
- It shall retain one newest pending frame per session and bounded replay histories, rejecting regressing sequences and stale source revisions.
- It shall enforce monotonic receipt-age freshness and maintain frame/receipt identity through the detector seam. Receipt age shall not be represented as aligned capture age.

Evidence: backend_phase1/README.md; stride_backend/main.py, ingestion.py, store.py, models.py, detector.py and tests in that milestone.

## Phase 2: continuous vision and sessions

- The service shall load a configured detector factory and dispatch work off the HTTP event loop without an unbounded inference queue.
- Vision controls shall support idle/active/paused/stopped, generation invalidation, terminal Stop, action-ID deduplication and optional generation checks.
- Latest results shall include current frame metadata, normalized objects, freshness, detector availability and operational counters. Stale/unavailable output shall not masquerade as live.
- Session login shall exchange a separate session secret for a signed, expiring HttpOnly cookie. Authorization shall bind requests to the requested session, check origins and separate UI access from camera credentials.
- Cookie-authenticated camera uploads shall preserve the Phase 1 multipart contract without exposing the hardware token to the browser.

Evidence: backend_phase2/README.md; stride_backend/auth.py, vision.py, worker.py, store.py, settings.py and tests/test_session_auth.py, tests/test_worker.py.

## Phase 3: checked routes and persistent memory

- SQLite shall store routes, ordered checkpoints, navigation progress, route events, action-idempotency records, guidance cues and historical sightings.
- Only checked routes shall start. Confirm shall advance one checkpoint; Repeat shall create a fresh cue without progress; Pause/Resume shall retain position in the sequence.
- Actions shall validate navigation identity, ownership and revision. Duplicate actions shall not double-advance, and replaying an old action shall not resurrect an old cue.
- Restart recovery shall retain confirmed progress, pause previously guiding routes, invalidate old cues and preserve blocked conditions.
- Sightings shall preserve provenance, frame/track identity and original observation times. Checkpoint context means the last manually confirmed checkpoint, not measured object location.

Evidence: backend_phase3/README.md; stride_backend/database.py, navigation.py, route_store.py, route_models.py, memory.py and corresponding tests.

## Later capabilities — keep phase attribution accurate

Controller pairing, telemetry freshness, obstacle hysteresis and command TTL/ACKs belong to Phase 4, implemented inside backend_phase3. Frontend integration and browser recovery checks belong to the frontend/Phase 5 work. Do not relabel those as completed Phase 1 features.
