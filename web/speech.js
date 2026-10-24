// STRIDE frontend — bounded speech scheduler.
//
// The backend authorizes and deduplicates events; we PLAY them. We do not
// synthesize speech from raw detection boxes. Rules implemented here:
//
//  * Dedupe by stable event_id across BOTH poll sources (/status and
//    /vision/latest) within a session.
//  * Priority: urgent obstacle/stop > fault > route > observation. A higher
//    priority event cancels the current lower-priority utterance.
//  * speechSynthesis.cancel() clears the browser queue, so we keep our OWN
//    bounded queue and re-drive it.
//  * Recheck generation/expiry/age/priority IMMEDIATELY before playback: a
//    result fresh at receipt can expire while queued. Live frame age > 1000 ms
//    is unspeakable.
//  * Drop expired low-priority events instead of flushing them after recovery.
//  * Speech is OFF until an explicit user gesture (enable/test) — required for
//    the capture client to stay silent and for mobile autoplay policies.

export const PRIORITY = Object.freeze({
  urgent: 4,
  obstacle: 4,
  stop: 4,
  fault: 3,
  route: 2,
  observation: 1,
});

const LIVE_UNSPEAKABLE_AGE_MS = 1000;
const MAX_QUEUE = 8; // bounded

export class SpeechScheduler {
  constructor({ clock, onState } = {}) {
    this.clock = clock;
    this.onState = onState || (() => {});
    this.enabled = false; // requires user gesture
    this.supported = typeof window !== "undefined" && "speechSynthesis" in window;
    this.consumed = new Set(); // event_ids already accepted
    this.queue = []; // bounded, priority-ordered
    this.current = null; // {event, priority}
    this._speaking = false;
  }

  rank(event) {
    return PRIORITY[event.priority] ?? PRIORITY[event.kind] ?? 0;
  }

  // User-gesture enable. Speaks a short confirmation so the user verifies audio
  // routing (e.g. AirPods) before relying on it.
  enable() {
    this.enabled = true;
    if (this.supported) {
      try {
        const u = new SpeechSynthesisUtterance("Speech enabled.");
        window.speechSynthesis.speak(u);
      } catch {
        /* ignore */
      }
    }
    this._emit("enabled");
  }

  disable() {
    this.enabled = false;
    this.clear();
    if (this.supported) window.speechSynthesis.cancel();
    this._emit("disabled");
  }

  // Offer an event from any poll source. Returns true if newly accepted.
  offer(event) {
    if (!event || !event.event_id) return false;
    if (this.consumed.has(event.event_id)) return false;
    if (!this._fresh(event, "accept")) {
      // Record expired low-priority events as consumed so a late duplicate poll
      // cannot replay them, but do not queue.
      this.consumed.add(event.event_id);
      return false;
    }
    this.consumed.add(event.event_id);

    const incomingRank = this.rank(event);
    // Higher priority cancels the current lower-priority utterance.
    if (this.current && incomingRank > this.rank(this.current.event)) {
      this._cancelCurrent();
    }
    this.queue.push({ event, rank: incomingRank });
    // Keep queue bounded + priority ordered (stable by insertion for equal rank).
    this.queue.sort((a, b) => b.rank - a.rank);
    if (this.queue.length > MAX_QUEUE) {
      // Drop the lowest-priority overflow.
      this.queue.length = MAX_QUEUE;
    }
    this._drive();
    return true;
  }

  // Freshness / eligibility recheck. live events older than 1000ms unspeakable.
  _fresh(event, phase) {
    const serverNow = this.clock ? this.clock.serverNow() : Date.now();
    if (event.expires_ms != null && serverNow >= event.expires_ms) return false;
    // For observation/vision events, enforce the strict live cutoff using age.
    if (event.kind === "observation" || event.priority === "observation") {
      const age = event.age_ms != null ? event.age_ms : this.clock ? this.clock.ageMs(event.created_ms) : null;
      if (age != null && age > LIVE_UNSPEAKABLE_AGE_MS) return false;
    }
    return true;
  }

  _drive() {
    if (!this.enabled || !this.supported) return;
    if (this._speaking) return;
    // Pop the highest-priority still-fresh event.
    while (this.queue.length) {
      const next = this.queue.shift();
      if (!this._fresh(next.event, "play")) continue; // expired while queued
      this._speak(next);
      return;
    }
  }

  _speak(item) {
    this.current = item;
    this._speaking = true;
    this._emit("speaking", item.event);
    const u = new SpeechSynthesisUtterance(item.event.text || "");
    u.onend = () => {
      this._speaking = false;
      this.current = null;
      this._emit("idle");
      this._drive();
    };
    u.onerror = () => {
      this._speaking = false;
      this.current = null;
      this._emit("idle");
      this._drive();
    };
    try {
      window.speechSynthesis.speak(u);
    } catch {
      this._speaking = false;
      this.current = null;
    }
  }

  _cancelCurrent() {
    if (this.supported) window.speechSynthesis.cancel();
    this._speaking = false;
    this.current = null;
  }

  // Clear queue + current without flushing (used on pause/stop/hide/source switch).
  clear() {
    this.queue = [];
    this._cancelCurrent();
    this._emit("idle");
  }

  // On source/session switch, forget consumed IDs so a fresh source can speak,
  // but clear anything pending from the old source first.
  resetForSource() {
    this.clear();
    this.consumed.clear();
  }

  _emit(state, event) {
    this.onState({ state, enabled: this.enabled, supported: this.supported, event: event || null });
  }
}
