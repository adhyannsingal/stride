// STRIDE frontend — camera capture loop.
//
// Capture lifecycle requirements:
//  * NEVER call getUserMedia on load. Only after the explicit
//    "Use this device's camera" gesture (producer selection).
//  * Prefer rear camera (facingMode {ideal:'environment'}); allow device
//    selection on Mac. Capture ORIGINAL unmirrored pixels; preview mirroring
//    must not reverse cue semantics.
//  * Start 640x480, target <=5 uploads/s. Keep ONE request in flight; drop
//    obsolete captures. Never grow a backlog.
//  * Cancel pending work and stop tracks on pause/stop/page-hide; invalidate a
//    local generation so late responses from a retired selection are ignored.

const TARGET_HZ = 5;
const MIN_INTERVAL_MS = 1000 / TARGET_HZ;

export class CameraLoop {
  constructor({ api, videoEl, onUpload, onError, getContext }) {
    this.api = api;
    this.video = videoEl;
    this.onUpload = onUpload || (() => {});
    this.onError = onError || (() => {});
    this.getContext = getContext; // () => { sessionId, deviceId, bootId, sourceRevision }
    this.stream = null;
    this.running = false;
    this.inFlight = false;
    this.sequence = 0;
    this.generation = 0; // bumped on stop/source-switch to invalidate late work
    this.bootId = "boot-" + Math.random().toString(16).slice(2, 10);
    this._timer = null;
    this._canvas = document.createElement("canvas");
    this._canvas.width = 640;
    this._canvas.height = 480;
  }

  get active() {
    return this.running && !!this.stream;
  }

  // Explicit producer gesture. Requests permission; returns device info.
  async enableCameraProducer(deviceId) {
    const constraints = {
      audio: false,
      video: deviceId
        ? { deviceId: { exact: deviceId }, width: { ideal: 640 }, height: { ideal: 480 } }
        : { facingMode: { ideal: "environment" }, width: { ideal: 640 }, height: { ideal: 480 } },
    };
    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    this.stream = stream;
    this.video.srcObject = stream;
    await this.video.play();
    const track = stream.getVideoTracks()[0];
    const settings = track ? track.getSettings() : {};
    return { deviceId: settings.deviceId || deviceId || null, label: track ? track.label : "" };
  }

  async listVideoDevices() {
    if (!navigator.mediaDevices?.enumerateDevices) return [];
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices.filter((d) => d.kind === "videoinput");
  }

  // Begin the upload loop. Requires the producer to already be enabled.
  start() {
    if (!this.stream) throw new Error("Enable the camera producer first.");
    this.running = true;
    this.generation += 1;
    this._schedule(0);
  }

  pause() {
    this.running = false;
    this.generation += 1; // ignore late responses
    if (this._timer) clearTimeout(this._timer);
    this._timer = null;
  }

  // Full stop: release the camera too.
  stop() {
    this.pause();
    if (this.stream) {
      for (const track of this.stream.getTracks()) track.stop();
      this.stream = null;
    }
    this.video.srcObject = null;
    this.inFlight = false;
  }

  _schedule(delay) {
    if (!this.running) return;
    this._timer = setTimeout(() => this._tick(), delay);
  }

  async _tick() {
    if (!this.running) return;
    if (this.inFlight) {
      // Drop this slot; keep exactly one request in flight.
      this._schedule(MIN_INTERVAL_MS);
      return;
    }
    const ctx = this.getContext();
    if (!ctx || !ctx.sessionId) {
      this._schedule(MIN_INTERVAL_MS);
      return;
    }
    const gen = this.generation;
    const t0 = performance.now();
    let blob;
    try {
      blob = await this._capture();
    } catch (err) {
      this.onError(err);
      this._schedule(MIN_INTERVAL_MS);
      return;
    }
    if (gen !== this.generation || !this.running) return; // invalidated mid-capture

    this.inFlight = true;
    this.sequence += 1;
    const frameId = "frame-" + this.bootId + "-" + this.sequence;
    const capturedMs = this.api.clock.serverNow();
    try {
      const receipt = await this.api.uploadFrame({
        sessionId: ctx.sessionId,
        deviceId: ctx.deviceId,
        bootId: this.bootId,
        frameId,
        sequence: this.sequence,
        capturedMs,
        sourceRevision: ctx.sourceRevision,
        blob,
      });
      if (gen === this.generation) this.onUpload(receipt);
    } catch (err) {
      if (gen === this.generation) this.onError(err);
    } finally {
      this.inFlight = false;
      const elapsed = performance.now() - t0;
      const wait = Math.max(0, MIN_INTERVAL_MS - elapsed);
      this._schedule(wait);
    }
  }

  // Draw the current video frame to a 640x480 JPEG, UNMIRRORED (original pixels).
  _capture() {
    const v = this.video;
    if (!v.videoWidth) return Promise.reject(new Error("Camera has no frame yet."));
    const g = this._canvas.getContext("2d");
    g.setTransform(1, 0, 0, 1, 0, 0); // no mirroring in captured pixels
    g.drawImage(v, 0, 0, this._canvas.width, this._canvas.height);
    return new Promise((resolve, reject) => {
      this._canvas.toBlob(
        (b) => (b ? resolve(b) : reject(new Error("Failed to encode JPEG."))),
        "image/jpeg",
        0.8
      );
    });
  }
}
