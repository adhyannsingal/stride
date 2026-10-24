// Headless logic tests for STRIDE frontend pure modules.
// Run: node tests/browser/logic.test.mjs
// These exercise fixtures (route + vision state machines) and the speech
// scheduler (dedupe, priority, expiry). Camera/DOM flows are tested in-browser.

import assert from "node:assert/strict";

// --- minimal browser stubs so speech.js can load under Node ---
let spoken = [];
let cancels = 0;
globalThis.window = {
  speechSynthesis: {
    speak(u) {
      spoken.push(u.text);
      // Simulate async completion so the queue drains.
      if (u.onend) queueMicrotask(() => u.onend());
    },
    cancel() {
      cancels += 1;
    },
  },
};
globalThis.SpeechSynthesisUtterance = class {
  constructor(text) {
    this.text = text;
    this.onend = null;
    this.onerror = null;
  }
};

const { Fixtures } = await import("../../web/fixtures.js");
const { SpeechScheduler, PRIORITY } = await import("../../web/speech.js");

let passed = 0;
function test(name, fn) {
  return Promise.resolve()
    .then(fn)
    .then(() => {
      passed += 1;
      console.log("  ok -", name);
    })
    .catch((err) => {
      console.error("  FAIL -", name, "\n   ", err.message);
      process.exitCode = 1;
    });
}

// ---------------- Fixtures: route state machine ----------------
await test("route start -> guiding at checkpoint 0", () => {
  const f = new Fixtures();
  const r = f.routeAction({ action: "start", routeId: "r" });
  assert.equal(r.route.state, "guiding");
  assert.equal(r.route.checkpoint_index, 0);
  assert.ok(r.speech_event, "start emits a speech event");
});

await test("confirm advances; repeat does NOT advance", () => {
  const f = new Fixtures();
  f.routeAction({ action: "start", routeId: "r" });
  const c = f.routeAction({ action: "confirm" });
  assert.equal(c.route.checkpoint_index, 1);
  const rep = f.routeAction({ action: "repeat" });
  assert.equal(rep.route.checkpoint_index, 1, "repeat keeps the same checkpoint");
});

await test("final confirm completes once (3-step route)", () => {
  const f = new Fixtures();
  f.routeAction({ action: "start", routeId: "r" }); // idx 0
  f.routeAction({ action: "confirm" }); // idx 1
  f.routeAction({ action: "confirm" }); // idx 2 (last)
  const done = f.routeAction({ action: "confirm" }); // -> completed
  assert.equal(done.route.state, "completed");
  // Confirming again stays completed (completes once, no index overflow).
  const again = f.routeAction({ action: "confirm" });
  assert.equal(again.route.state, "completed");
  assert.equal(again.route.checkpoint_index, 2);
});

await test("pause/resume toggles guiding<->paused; stop resets", () => {
  const f = new Fixtures();
  f.routeAction({ action: "start", routeId: "r" });
  assert.equal(f.routeAction({ action: "pause" }).route.state, "paused");
  assert.equal(f.routeAction({ action: "resume" }).route.state, "guiding");
  const s = f.routeAction({ action: "stop" });
  assert.equal(s.route.state, "idle");
  assert.equal(s.route.checkpoint_index, null);
});

// ---------------- Fixtures: vision + revision ----------------
await test("vision is paused until start; live after start", () => {
  const f = new Fixtures();
  assert.equal(f.visionLatest("s").status, "paused");
  f.visionControl({ action: "start" });
  assert.equal(f.visionLatest("s").status, "live");
});

await test("camera selection increments source_revision and clears vision", () => {
  const f = new Fixtures();
  f.visionControl({ action: "start" });
  const before = f.visionLatest("s").source_revision;
  f.selectCamera("s", "browser_camera", "cam-2");
  const after = f.visionLatest("s");
  assert.equal(after.source_revision, before + 1);
  assert.equal(after.status, "paused", "source switch clears live results");
});

await test("live vision_latest has canonical xyxy box with min<max", () => {
  const f = new Fixtures();
  f.visionControl({ action: "start" });
  const v = f.visionLatest("s");
  const [x1, y1, x2, y2] = v.objects[0].box;
  assert.ok(x1 < x2 && y1 < y2, "box is min<max");
  assert.ok([x1, y1, x2, y2].every((n) => n >= 0 && n <= 1), "box normalized 0..1");
});

// ---------------- Speech scheduler ----------------
function freshEvent(id, priority, extra = {}) {
  const now = Date.now();
  return { event_id: id, priority, kind: priority, text: id, created_ms: now, expires_ms: now + 5000, ...extra };
}
const clockStub = { serverNow: () => Date.now(), ageMs: () => 0, synced: true };

await test("dedupe: same event_id offered twice accepted once", () => {
  spoken = [];
  const sch = new SpeechScheduler({ clock: clockStub });
  sch.enable();
  spoken = []; // drop the "Speech enabled." utterance
  assert.equal(sch.offer(freshEvent("e1", "route")), true);
  assert.equal(sch.offer(freshEvent("e1", "route")), false, "duplicate rejected");
});

await test("expired event is not queued and marked consumed", () => {
  const sch = new SpeechScheduler({ clock: clockStub });
  sch.enable();
  const now = Date.now();
  const expired = { event_id: "ex", priority: "route", kind: "route", text: "x", created_ms: now - 10000, expires_ms: now - 1 };
  assert.equal(sch.offer(expired), false);
  assert.ok(sch.consumed.has("ex"), "expired event id recorded to block replay");
});

await test("priority ranking: urgent > fault > route > observation", () => {
  assert.ok(PRIORITY.urgent > PRIORITY.fault);
  assert.ok(PRIORITY.fault > PRIORITY.route);
  assert.ok(PRIORITY.route > PRIORITY.observation);
});

await test("stale live observation (age>1000ms) is unspeakable", () => {
  const staleClock = { serverNow: () => Date.now(), ageMs: () => 1500, synced: true };
  const sch = new SpeechScheduler({ clock: staleClock });
  sch.enable();
  const now = Date.now();
  const obs = { event_id: "o1", priority: "observation", kind: "observation", text: "chair", created_ms: now - 1500, expires_ms: now + 5000, age_ms: 1500 };
  assert.equal(sch.offer(obs), false, "age>1000ms observation dropped");
});

await test("resetForSource clears consumed ids so new source can speak", () => {
  const sch = new SpeechScheduler({ clock: clockStub });
  sch.enable();
  sch.offer(freshEvent("e2", "route"));
  assert.ok(sch.consumed.has("e2"));
  sch.resetForSource();
  assert.equal(sch.consumed.size, 0);
});

console.log(`\n${passed} checks passed.`);
