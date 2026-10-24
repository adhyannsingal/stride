// STRIDE frontend — orchestrator.
//
// Wires the API adapter, camera loop and speech scheduler to the DOM. Renders
// AUTHORITATIVE server state (never increments route progress locally). Polls
// /status and /vision/latest without overlap, backs off on failure, aborts on
// page hide, and ignores stale (lower state_seq / old source_revision) data.

import { StrideApi, Mode } from "./api.js";
import { SpeechScheduler } from "./speech.js";
import { CameraLoop } from "./camera.js";

const $ = (id) => document.getElementById(id);
const body = document.body;

const STATUS_INTERVAL_MS = 250;
const VISION_INTERVAL_MS = 200; // 5 Hz while active

const state = {
  connected: false,
  role: "viewer", // viewer | camera
  sessionId: null,
  deviceId: "browser-camera-1",
  sourceRevision: 1,
  lastStatusSeq: -1,
  lastVisionSeq: -1,
  visionActive: false,
  dropped: 0,
  routes: [],
  selectedRouteId: null,
};

const api = new StrideApi({ mode: Mode.FIXTURE });
const speech = new SpeechScheduler({
  clock: api.clock,
  onState: ({ state: s, enabled }) => {
    $("speech-status").textContent = !enabled
      ? "Speech off."
      : s === "speaking"
      ? "Speaking…"
      : s === "enabled"
      ? "Speech enabled."
      : "Speech ready.";
  },
});

const camera = new CameraLoop({
  api,
  videoEl: $("video"),
  getContext: () => ({
    sessionId: state.sessionId,
    deviceId: state.deviceId,
    sourceRevision: state.sourceRevision,
  }),
  onUpload: () => {},
  onError: (err) => {
    // A capture/upload failure is surfaced, never hidden behind a fixture.
    $("connect-status").textContent = "Upload error: " + err.message;
  },
});

// ---- polling loops (no overlap, abort on hide) ----------------------------
let statusTimer = null;
let visionTimer = null;
let statusBusy = false;
let visionBusy = false;
let statusBackoff = STATUS_INTERVAL_MS;

async function pollStatus() {
  if (statusBusy || !state.connected || document.hidden) return;
  statusBusy = true;
  try {
    const s = await api.status(state.sessionId);
    if (s.state_seq >= state.lastStatusSeq) {
      state.lastStatusSeq = s.state_seq;
      renderStatus(s);
      if (s.speech_event) speech.offer(s.speech_event);
    }
    statusBackoff = STATUS_INTERVAL_MS;
    setHealth("ok");
  } catch (err) {
    setHealth("down");
    statusBackoff = Math.min(statusBackoff * 2, 4000); // back off on failure
    $("connect-status").textContent = "Status error: " + err.message;
  } finally {
    statusBusy = false;
  }
}

async function pollVision() {
  if (visionBusy || !state.connected || !state.visionActive || document.hidden) return;
  visionBusy = true;
  try {
    const v = await api.visionLatest(state.sessionId);
    // Ignore stale revisions and out-of-order sequences.
    if (v.source_revision != null && v.source_revision < state.sourceRevision) return;
    if (v.state_seq != null && v.state_seq < state.lastVisionSeq) return;
    if (v.state_seq != null) state.lastVisionSeq = v.state_seq;
    renderVision(v);
    if (v.speech_event) speech.offer(v.speech_event);
  } catch (err) {
    $("m-status").textContent = "error";
  } finally {
    visionBusy = false;
  }
}

function startLoops() {
  stopLoops();
  const tickStatus = async () => {
    await pollStatus();
    statusTimer = setTimeout(tickStatus, statusBackoff);
  };
  const tickVision = async () => {
    await pollVision();
    visionTimer = setTimeout(tickVision, VISION_INTERVAL_MS);
  };
  tickStatus();
  tickVision();
}

function stopLoops() {
  if (statusTimer) clearTimeout(statusTimer);
  if (visionTimer) clearTimeout(visionTimer);
  statusTimer = visionTimer = null;
}

// Page hide: a viewer stops only its own polling/playback. A capture client
// pauses its capture and lets freshness expiry suppress old output.
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    speech.clear();
    if (state.role === "camera") camera.pause();
  }
});

// ---- rendering ------------------------------------------------------------
function setHealth(h) {
  $("health-dot").dataset.health = h;
}

function renderStatus(s) {
  if (s.camera) {
    $("source-label").textContent = "source: " + (s.camera.source || "—");
    $("m-origin").textContent = s.camera.origin || "—";
    if (s.camera.source_revision != null) {
      // Adopt a server-advanced revision (e.g. after another client switched).
      if (s.camera.source_revision > state.sourceRevision) {
        state.sourceRevision = s.camera.source_revision;
        speech.resetForSource();
      }
    }
  }
  if (s.feedback) {
    const f = s.feedback;
    $("f-distance").textContent = f.valid && f.distance_cm != null ? Math.round(f.distance_cm) + " cm" : "—";
    $("f-alert").textContent = f.alert || "none";
    $("f-source").textContent = (f.source || "—") + (f.connected ? "" : " (offline)");
    $("f-ack").textContent = f.ack_state || "—";
  }
  if (s.route) renderRoute(s.route);
  if (s.vision) {
    $("m-status").textContent = s.vision.status || "—";
  }
}

function renderRoute(route) {
  const st = route.state || "idle";
  $("route-state").textContent = st[0].toUpperCase() + st.slice(1) + ".";
  $("route-instruction").textContent = route.instruction || "—";
  const guiding = st === "guiding";
  const paused = st === "paused";
  const active = st !== "idle" && st !== "completed";
  $("btn-start").disabled = active;
  $("btn-confirm").disabled = !guiding;
  $("btn-repeat").disabled = !(guiding || paused);
  $("btn-pause").disabled = !guiding;
  $("btn-resume").disabled = !paused;
  $("btn-stop").disabled = !active;
}

function renderVision(v) {
  $("m-status").textContent = v.status || "—";
  $("m-hz").textContent = v.result_hz != null ? v.result_hz.toFixed(1) + " Hz" : "—";
  $("m-origin").textContent = v.origin || "—";
  // Recompute age with aligned clock; if stale, treat as unavailable for speech.
  const age = v.completed_ms != null ? api.clock.ageMs(v.completed_ms) : v.age_ms;
  $("m-age").textContent = age != null ? Math.round(age) + " ms" : "—";

  const boxes = $("boxes");
  boxes.replaceChildren();
  const stale = v.status !== "live" || (age != null && age > 1000);
  if (!stale && Array.isArray(v.objects)) {
    for (const obj of v.objects) {
      if (!obj.box) continue;
      const [x1, y1, x2, y2] = obj.box;
      const el = document.createElement("div");
      el.className = "box";
      el.style.left = x1 * 100 + "%";
      el.style.top = y1 * 100 + "%";
      el.style.width = (x2 - x1) * 100 + "%";
      el.style.height = (y2 - y1) * 100 + "%";
      const label = document.createElement("span");
      label.textContent = obj.label + (obj.score != null ? " " + Math.round(obj.score * 100) + "%" : "");
      el.append(label);
      boxes.append(el);
    }
  }
  if (stale) {
    // >1s with no fresh results → live vision unavailable; clear overlays.
    $("m-status").textContent = v.status === "live" ? "stale" : v.status;
  }
}

function renderRoutes(routes) {
  state.routes = routes;
  const sel = $("route-select");
  sel.replaceChildren();
  for (const r of routes) {
    const opt = document.createElement("option");
    opt.value = r.route_id;
    opt.textContent = r.name + (r.is_demo ? " (demo)" : "");
    sel.append(opt);
  }
  if (routes.length) state.selectedRouteId = routes[0].route_id;
}

// ---- connect flow ---------------------------------------------------------
async function connect() {
  const mode = $("mode-select").value === "real" ? Mode.REAL : Mode.FIXTURE;
  api.setMode(mode);
  api.baseUrl = $("base-url").value.trim().replace(/\/$/, "");
  body.dataset.mode = mode;
  $("mode-badge").textContent = mode === Mode.REAL ? "Real" : "Fixtures";
  $("mode-badge").className = "badge " + (mode === Mode.REAL ? "badge-real" : "badge-fixture");

  $("connect-status").textContent = "Connecting…";
  try {
    const health = await api.health();
    setHealth(health.status === "ok" || health.status ? "ok" : "down");
    await api.auth($("access-code").value);
    await api.syncClock();

    const existing = $("session-id").value.trim();
    if (existing) {
      state.sessionId = existing; // join existing session (side-effect free)
    } else {
      const session = await api.createSession({ mode: "training", cameraOrigin: "browser_camera" });
      state.sessionId = session.session_id;
      state.sourceRevision = session.source_revision ?? 1;
      $("session-id").value = state.sessionId;
    }

    const routes = await api.listRoutes();
    renderRoutes(routes.routes || []);

    state.connected = true;
    $("connect-status").textContent = "Connected. Session " + state.sessionId;
    startLoops();
  } catch (err) {
    state.connected = false;
    setHealth("down");
    $("connect-status").textContent = "Connect failed: " + err.message;
  }
}

// ---- role handling --------------------------------------------------------
function setRole(role) {
  state.role = role;
  body.dataset.role = role;
  $("role-viewer").setAttribute("aria-pressed", role === "viewer");
  $("role-camera").setAttribute("aria-pressed", role === "camera");
  $("role-label").textContent = role === "camera" ? "Camera source" : "Viewer / audio";
  $("camera-producer").hidden = role !== "camera";
  if (role === "viewer") {
    // Switching to viewer never grabs the camera; release if we had it.
    camera.stop();
    $("stage").classList.remove("is-live");
    $("video").classList.remove("is-live");
    $("producer-label").textContent = "Viewer role. This device does not capture.";
  } else {
    $("producer-label").textContent = "Camera role selected. Tap the button to grant access.";
    populateCameraDevices();
  }
}

async function populateCameraDevices() {
  try {
    const devices = await camera.listVideoDevices();
    const sel = $("camera-device");
    sel.replaceChildren();
    const auto = document.createElement("option");
    auto.value = "";
    auto.textContent = "Rear camera (auto)";
    sel.append(auto);
    devices.forEach((d, i) => {
      const opt = document.createElement("option");
      opt.value = d.deviceId;
      opt.textContent = d.label || "Camera " + (i + 1);
      sel.append(opt);
    });
  } catch {
    /* enumerateDevices may require permission first */
  }
}

async function useThisCamera() {
  try {
    const deviceId = $("camera-device").value || null;
    const info = await camera.enableCameraProducer(deviceId);
    $("video").classList.add("is-live");
    $("stage").classList.add("is-live");
    $("producer-label").textContent = "Producer: " + (info.label || info.deviceId || "camera");
    // Bind this producer as the active browser camera source.
    if (!api.isFixture) {
      const sel = await api.selectCamera(state.sessionId, "browser_camera", info.deviceId);
      state.sourceRevision = sel.source_revision ?? state.sourceRevision;
    }
    await populateCameraDevices();
  } catch (err) {
    $("producer-label").textContent = "Camera denied/unavailable: " + err.message;
    $("stage-empty").textContent = "Camera permission was denied.";
  }
}

// ---- vision + route actions -----------------------------------------------
async function startNavigation() {
  try {
    // Start vision once; begin browser capture only if this is the camera role.
    await api.visionControl({ sessionId: state.sessionId, action: "start" });
    state.visionActive = true;
    if (state.role === "camera" && camera.stream) camera.start();
    await routeAction("start");
  } catch (err) {
    $("route-state").textContent = "Start failed: " + err.message;
  }
}

async function routeAction(action) {
  try {
    if (action === "start") {
      const routeId = $("route-select").value || state.selectedRouteId;
      const r = await api.routeAction({ sessionId: state.sessionId, action: "start", routeId });
      applyRouteResult(r);
    } else {
      const r = await api.routeAction({ sessionId: state.sessionId, action });
      applyRouteResult(r);
      if (action === "stop") {
        state.visionActive = false;
        await api.visionControl({ sessionId: state.sessionId, action: "stop" });
        camera.pause();
        speech.clear();
      }
      if (action === "pause") {
        state.visionActive = false;
        await api.visionControl({ sessionId: state.sessionId, action: "pause" });
        camera.pause();
      }
      if (action === "resume") {
        state.visionActive = true;
        await api.visionControl({ sessionId: state.sessionId, action: "resume" });
        if (state.role === "camera" && camera.stream) camera.start();
      }
    }
  } catch (err) {
    $("route-state").textContent = action + " failed: " + err.message;
  }
}

function applyRouteResult(r) {
  if (r.route) renderRoute(r.route);
  if (r.speech_event) speech.offer(r.speech_event);
}

async function find() {
  const target = $("find-target").value.trim();
  if (!target) return;
  try {
    const frameId = "find-" + Date.now();
    const res = await api.perception({ sessionId: state.sessionId, frameId, task: "find", target });
    if (res.status === "ok") {
      $("find-status").textContent = target + " found (" + (res.objects[0]?.position || "?") + ").";
      if (res.speakable && res.speech_event) speech.offer(res.speech_event);
    } else if (res.status === "not_found") {
      $("find-status").textContent = target + " not found in the latest frame.";
    } else {
      $("find-status").textContent = "Result expired. Capture again.";
    }
  } catch (err) {
    $("find-status").textContent = "Find error: " + err.message;
  }
}

// ---- wire up DOM ----------------------------------------------------------
$("btn-connect").addEventListener("click", connect);
$("role-viewer").addEventListener("click", () => setRole("viewer"));
$("role-camera").addEventListener("click", () => setRole("camera"));
$("btn-use-camera").addEventListener("click", useThisCamera);
$("btn-speech").addEventListener("click", () => speech.enable());
$("btn-start").addEventListener("click", startNavigation);
$("btn-confirm").addEventListener("click", () => routeAction("confirm"));
$("btn-repeat").addEventListener("click", () => routeAction("repeat"));
$("btn-pause").addEventListener("click", () => routeAction("pause"));
$("btn-resume").addEventListener("click", () => routeAction("resume"));
$("btn-stop").addEventListener("click", () => routeAction("stop"));
$("btn-find").addEventListener("click", find);
$("route-select").addEventListener("change", (e) => {
  state.selectedRouteId = e.target.value;
});
$("mode-select").addEventListener("change", (e) => {
  body.dataset.mode = e.target.value;
});

// Allow ?fixtures=1 to preselect fixture mode explicitly (dev convenience).
const params = new URLSearchParams(location.search);
if (params.get("fixtures") === "0") $("mode-select").value = "real";

setRole("viewer");

// Expose a tiny hook for headless/browser tests to introspect state.
window.__stride = { state, api, speech, camera };
