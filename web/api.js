// STRIDE frontend — single API adapter.
//
// Every backend call in the app goes through this module so that fixtures and
// the real backend share one code path. Fixtures are an
// explicit, selectable development mode — NEVER a silent fallback after a real
// API error. If the real backend errors, the error surfaces; we do not quietly
// serve a fixture in its place.
//
// This historical scaffold follows the original API examples.
// Coordinate interface changes rather
// than renaming here.

import { Fixtures } from "./fixtures.js";

export const Mode = Object.freeze({ REAL: "real", FIXTURE: "fixture" });

// ---- clock alignment -------------------------------------------------------
// We cannot claim live freshness without an aligned clock. /time + request RTT
// gives a conservative server/client offset. If we never align, callers must
// treat age as unknown and expose "unavailable", not false "live".
class Clock {
  constructor() {
    this.offsetMs = null; // serverNow - clientNow
    this.rttMs = null;
    this.synced = false;
  }
  // Align using one round trip. offset = server_ms - (t0 + rtt/2).
  align(serverMs, t0, t1) {
    const rtt = Math.max(0, t1 - t0);
    this.rttMs = rtt;
    this.offsetMs = serverMs - (t0 + rtt / 2);
    this.synced = true;
    return this.offsetMs;
  }
  // Best estimate of server epoch for the current client wall time.
  serverNow() {
    const now = Date.now();
    return this.synced ? now + this.offsetMs : now;
  }
  // Age of a server-stamped event, using aligned time. Null when not synced.
  ageMs(serverStampMs) {
    if (!this.synced || serverStampMs == null) return null;
    return Math.max(0, this.serverNow() - serverStampMs);
  }
}

export class StrideApi {
  constructor({ mode = Mode.FIXTURE, baseUrl = "" } = {}) {
    this.mode = mode;
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.clock = new Clock();
    this._fixtures = new Fixtures();
  }

  setMode(mode) {
    this.mode = mode === Mode.REAL ? Mode.REAL : Mode.FIXTURE;
  }

  get isFixture() {
    return this.mode === Mode.FIXTURE;
  }

  // ---- low-level fetch with same-origin cookies ----------------------------
  async _fetch(path, { method = "GET", headers = {}, body, raw = false, signal } = {}) {
    const url = this.baseUrl + path;
    const res = await fetch(url, {
      method,
      headers,
      body,
      credentials: "same-origin", // auth cookie; no tokens in JS
      cache: "no-store",
      signal,
    });
    const text = await res.text();
    let payload = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = { error: { code: "bad_json", message: text.slice(0, 200), retryable: false } };
      }
    }
    if (!res.ok) {
      const err = new Error(payload?.error?.message || `HTTP ${res.status}`);
      err.status = res.status;
      err.code = payload?.error?.code;
      err.retryable = payload?.error?.retryable ?? false;
      err.payload = payload;
      throw err;
    }
    return raw ? { res, payload } : payload;
  }

  // ---- time / clock --------------------------------------------------------
  async syncClock() {
    if (this.isFixture) {
      const serverMs = this._fixtures.time().server_ms;
      this.clock.align(serverMs, Date.now(), Date.now());
      return this.clock;
    }
    const t0 = Date.now();
    // Backend (software branch) exposes /time as { server_ms }.
    const payload = await this._fetch("/time");
    const t1 = Date.now();
    const serverMs = payload.server_ms ?? payload.server_time_ms;
    this.clock.align(serverMs, t0, t1);
    return this.clock;
  }

  // ---- health --------------------------------------------------------------
  async health() {
    if (this.isFixture) return this._fixtures.health();
    return this._fetch("/health");
  }

  // ---- auth / sessions -----------------------------------------------------
  async auth(accessCode) {
    if (this.isFixture) return this._fixtures.auth(accessCode);
    return this._fetch("/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_code: accessCode }),
    });
  }

  async createSession({ mode = "training", cameraOrigin = "browser_camera" } = {}) {
    if (this.isFixture) return this._fixtures.createSession({ mode, cameraOrigin });
    return this._fetch("/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_id: uuid(), mode, camera_origin: cameraOrigin }),
    });
  }

  async selectCamera(sessionId, cameraOrigin, cameraDeviceId) {
    if (this.isFixture) return this._fixtures.selectCamera(sessionId, cameraOrigin, cameraDeviceId);
    return this._fetch(`/sessions/${sessionId}/camera`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_id: uuid(), camera_origin: cameraOrigin, camera_device_id: cameraDeviceId }),
    });
  }

  // ---- routes --------------------------------------------------------------
  async listRoutes() {
    if (this.isFixture) return this._fixtures.listRoutes();
    return this._fetch("/routes");
  }

  async routeAction({ sessionId, action, routeId }) {
    if (this.isFixture) return this._fixtures.routeAction({ sessionId, action, routeId });
    return this._fetch("/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_id: uuid(), session_id: sessionId, action, route_id: routeId }),
    });
  }

  // ---- status --------------------------------------------------------------
  async status(sessionId) {
    if (this.isFixture) return this._fixtures.status(sessionId);
    return this._fetch(`/status?session_id=${encodeURIComponent(sessionId)}`);
  }

  // ---- frame upload --------------------------------------------------------
  // Raw image/jpeg per contract. Keeps ONE upload in flight; obsolete captures
  // are dropped by the caller before calling this.
  async uploadFrame({ sessionId, deviceId, bootId, frameId, sequence, capturedMs, sourceRevision, blob, signal }) {
    if (this.isFixture) return this._fixtures.uploadFrame({ frameId, capturedMs });
    const headers = {
      "Content-Type": "image/jpeg",
      "X-Session-Id": sessionId,
      "X-Device-Id": deviceId,
      "X-Boot-Id": bootId,
      "X-Frame-Id": frameId,
      "X-Sequence": String(sequence),
      "X-Captured-Ms": String(capturedMs),
      "X-Clock-Synced": String(this.clock.synced),
      "X-Source-Revision": String(sourceRevision),
    };
    return this._fetch("/frame", { method: "POST", headers, body: blob, signal });
  }

  // ---- vision --------------------------------------------------------------
  async visionControl({ sessionId, action }) {
    if (this.isFixture) return this._fixtures.visionControl({ sessionId, action });
    return this._fetch("/vision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_id: uuid(), session_id: sessionId, action }),
    });
  }

  async visionLatest(sessionId, signal) {
    if (this.isFixture) return this._fixtures.visionLatest(sessionId);
    return this._fetch(`/vision/latest?session_id=${encodeURIComponent(sessionId)}`, { signal });
  }

  // ---- perception (optional Gemini snapshot) -------------------------------
  async perception({ sessionId, frameId, task, target }) {
    if (this.isFixture) return this._fixtures.perception({ sessionId, frameId, task, target });
    return this._fetch("/perception", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action_id: uuid(), session_id: sessionId, frame_id: frameId, task, target }),
    });
  }

  // ---- memory --------------------------------------------------------------
  async memory(sessionId, kind = "sightings", limit = 20) {
    if (this.isFixture) return this._fixtures.memory(sessionId, kind, limit);
    return this._fetch(`/memory?session_id=${encodeURIComponent(sessionId)}&kind=${kind}&limit=${limit}`);
  }
}

// RFC4122-ish v4 UUID for action_id values (idempotency keys).
export function uuid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
