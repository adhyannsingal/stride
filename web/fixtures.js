// STRIDE frontend — explicit development fixtures.
//
// These are a SELECTABLE development mode only. The app enters fixture mode
// because the user picked it (or because the page was loaded with ?fixtures=1),
// never because a real API call failed. On a real-mode error the adapter throws
// and the UI shows the error; it does not quietly swap in a fixture.
//
// Shapes reflect the original API scaffold so the UI
// renders identically against fixtures and the real backend.

const DEMO_ROUTE_ID = "00000000-0000-4000-8000-000000000050";

const DEMO_ROUTE = {
  route_id: DEMO_ROUTE_ID,
  name: "Checked demo route",
  is_demo: true,
  steps: [
    { checkpoint_id: "A", instruction: "At the marked start, turn left toward checkpoint B.", pattern: "left" },
    { checkpoint_id: "B", instruction: "At checkpoint B, turn right toward checkpoint C.", pattern: "right" },
    { checkpoint_id: "C", instruction: "Checkpoint C reached. Route complete.", pattern: "stop" },
  ],
  return_steps: [],
};

export class Fixtures {
  constructor() {
    this._seq = 40;
    this._sourceRevision = 1;
    // route state machine
    this._route = { state: "idle", checkpoint_index: 0 };
    this._routeId = null;
    // vision state machine
    this._vision = "paused"; // paused | live | stale | unavailable
    this._visionStart = 0;
    this._lastEventId = null;
    this._frameCounter = 0;
  }

  _nextSeq() {
    this._seq += 1;
    return this._seq;
  }

  _now() {
    return Date.now();
  }

  time() {
    return { server_ms: this._now() };
  }

  health() {
    return {
      status: "ok",
      version: "fixture",
      commit: "fixture",
      provider_configured: true,
      note: "Fixture health. Not a real backend.",
    };
  }

  auth(accessCode) {
    if (!accessCode) {
      const err = new Error("Enter the access code.");
      err.status = 401;
      err.code = "bad_access_code";
      throw err;
    }
    return { authenticated: true };
  }

  createSession({ mode, cameraOrigin }) {
    return {
      session_id: "00000000-0000-4000-8000-000000000010",
      mode,
      source: "fixture",
      origin: cameraOrigin,
      command_generation: "00000000-0000-4000-8000-000000000040",
      device_bindings: {},
      source_revision: this._sourceRevision,
      state_seq: this._nextSeq(),
      server_time_ms: this._now(),
    };
  }

  selectCamera(sessionId, cameraOrigin, cameraDeviceId) {
    this._sourceRevision += 1; // selection change increments revision
    // A source switch clears old results.
    this._vision = "paused";
    return {
      session_id: sessionId,
      origin: cameraOrigin,
      camera_device_id: cameraDeviceId || null,
      source_revision: this._sourceRevision,
      state_seq: this._nextSeq(),
      server_time_ms: this._now(),
    };
  }

  listRoutes() {
    return { routes: [DEMO_ROUTE] };
  }

  // Authoritative route state machine. Repeat never advances; confirm advances;
  // final confirm completes once.
  routeAction({ action, routeId }) {
    const steps = DEMO_ROUTE.steps;
    let eventKind = "route";
    switch (action) {
      case "start":
        this._routeId = routeId || DEMO_ROUTE_ID;
        this._route = { state: "guiding", checkpoint_index: 0 };
        break;
      case "confirm":
        if (this._route.state === "guiding") {
          if (this._route.checkpoint_index >= steps.length - 1) {
            this._route = { state: "completed", checkpoint_index: steps.length - 1 };
          } else {
            this._route.checkpoint_index += 1;
          }
        }
        break;
      case "repeat":
        eventKind = "route"; // fresh repeat event, no index change
        break;
      case "pause":
        if (this._route.state === "guiding") this._route.state = "paused";
        break;
      case "resume":
        if (this._route.state === "paused") this._route.state = "guiding";
        break;
      case "stop":
        this._route = { state: "idle", checkpoint_index: 0 };
        this._routeId = null;
        break;
      default:
        break;
    }
    return this._routeState(eventKind, action);
  }

  _routeState(eventKind, action) {
    const steps = DEMO_ROUTE.steps;
    const idx = Math.min(this._route.checkpoint_index, steps.length - 1);
    const step = steps[idx];
    const active = this._route.state !== "idle";
    return {
      session_id: "00000000-0000-4000-8000-000000000010",
      state_seq: this._nextSeq(),
      server_time_ms: this._now(),
      route: {
        route_id: active ? this._routeId || DEMO_ROUTE_ID : null,
        state: this._route.state,
        checkpoint_index: active ? idx : null,
        checkpoint_id: active ? step.checkpoint_id : null,
        instruction: active ? step.instruction : null,
        pattern: active ? step.pattern : "none",
        overlay: "none",
      },
      speech_event:
        active && (action === "start" || action === "confirm" || action === "repeat" || action === "resume")
          ? {
              event_id: "evt-route-" + this._nextSeq(),
              kind: eventKind,
              priority: "route",
              text: step.instruction,
              created_ms: this._now(),
              expires_ms: this._now() + 8000,
            }
          : null,
    };
  }

  status(sessionId) {
    const routeState = this._routeState("route", "poll").route;
    return {
      session_id: sessionId || "00000000-0000-4000-8000-000000000010",
      state_seq: this._nextSeq(),
      server_time_ms: this._now(),
      mode: "training",
      route: routeState,
      camera: {
        origin: "browser_camera",
        source: "fixture",
        connected: true,
        age_ms: 200,
        source_revision: this._sourceRevision,
      },
      feedback: {
        origin: "simulator",
        source: "simulated",
        connected: true,
        valid: true,
        distance_cm: 120,
        age_ms: 100,
        alert: "none",
        ack_state: "unavailable",
      },
      perception: { provider: "gemini", available: true, busy: false, latest: null },
      vision: { status: this._vision, age_ms: this._vision === "live" ? 250 : null, result_hz: this._vision === "live" ? 5.0 : 0 },
      speech_event: null,
      haptic_event: null,
      memory: { durability: "local_sqlite", export_available: true },
    };
  }

  uploadFrame({ frameId, capturedMs }) {
    this._frameCounter += 1;
    return {
      frame_id: frameId,
      origin: "browser_camera",
      source: "fixture",
      source_revision: this._sourceRevision,
      captured_ms: capturedMs,
      received_ms: this._now(),
      clock_synced: true,
      width: 640,
      height: 480,
      server_time_ms: this._now(),
    };
  }

  visionControl({ action }) {
    if (action === "start" || action === "resume") {
      this._vision = "live";
      this._visionStart = this._now();
    } else if (action === "pause") {
      this._vision = "paused";
    } else if (action === "stop") {
      this._vision = "paused";
    }
    return {
      session_id: "00000000-0000-4000-8000-000000000010",
      status: this._vision,
      source_revision: this._sourceRevision,
      state_seq: this._nextSeq(),
      server_time_ms: this._now(),
    };
  }

  // Produces a contract-shaped /vision/latest. While live, emits a fresh frame
  // with an occasional new object event (deduplicated by event_id).
  visionLatest(sessionId) {
    const now = this._now();
    if (this._vision !== "live") {
      return {
        session_id: sessionId || "00000000-0000-4000-8000-000000000010",
        state_seq: this._nextSeq(),
        server_time_ms: now,
        status: this._vision, // paused | stale | unavailable
        source_revision: this._sourceRevision,
        origin: "browser_camera",
        source: "fixture",
        provider: "yolo",
        result_hz: 0,
        objects: [],
        speech_event: null,
      };
    }
    this._frameCounter += 1;
    const capturedMs = now - 150;
    const completedMs = now - 50;
    // New-object speech event every ~15 frames; otherwise null (do not narrate
    // every frame). Event has a short expiry so queued-but-expired is testable.
    let speechEvent = null;
    if (this._frameCounter % 15 === 0) {
      const id = "evt-vision-" + this._frameCounter;
      speechEvent = {
        event_id: id,
        kind: "observation",
        priority: "observation",
        text: "Chair on the left.",
        created_ms: now,
        expires_ms: now + 1000,
      };
      this._lastEventId = id;
    }
    return {
      session_id: sessionId || "00000000-0000-4000-8000-000000000010",
      state_seq: this._nextSeq(),
      server_time_ms: now,
      frame_id: "frame-" + this._frameCounter,
      captured_ms: capturedMs,
      completed_ms: completedMs,
      age_ms: now - completedMs,
      source_revision: this._sourceRevision,
      origin: "browser_camera",
      source: "fixture",
      status: "live",
      provider: "yolo",
      result_hz: 5.0,
      objects: [
        { track_id: "track-1", label: "chair", score: 0.83, box: [0.1, 0.2, 0.4, 0.9], position: "left" },
      ],
      speech_event: speechEvent,
    };
  }

  perception({ frameId, task, target }) {
    const found = task !== "find" || (target && /chair|mug|door/i.test(target));
    return {
      observation_id: "obs-" + this._nextSeq(),
      status: found ? "ok" : "not_found",
      origin: "browser_camera",
      source: "fixture",
      provider: "fixture",
      frame_id: frameId,
      source_revision: this._sourceRevision,
      captured_ms: this._now() - 200,
      completed_ms: this._now(),
      age_ms: 200,
      latency_ms: 180,
      objects: found ? [{ label: target || "chair", box: [0.35, 0.1, 0.7, 0.85], position: "center" }] : [],
      speakable: found,
      speech_event: found
        ? {
            event_id: "evt-perc-" + this._nextSeq(),
            kind: "observation",
            priority: "observation",
            text: (target || "chair") + " in the center of view.",
            created_ms: this._now(),
            expires_ms: this._now() + 5000,
          }
        : null,
    };
  }

  memory(sessionId, kind) {
    if (kind === "routes") return { records: [DEMO_ROUTE] };
    return {
      records: [
        {
          kind: "sighting",
          label: "chair",
          source: "fixture",
          age_ms: 42000,
          checkpoint_id: "A",
          captured_ms: this._now() - 42000,
        },
      ],
    };
  }
}
