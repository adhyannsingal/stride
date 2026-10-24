// STRIDE frontend — live-result polling controller (TypeScript).
//
// Polls /status and /vision/latest without overlap, backs off on failure,
// aborts on page hide, ignores stale (lower state_seq / old source_revision)
// data, suppresses stale vision results (>1000 ms), and forwards backend speech
// events to the speech controller (which dedupes by event_id).

import type { StrideApi } from './api'
import type { SpeechController } from './speech'
import type { StatusResponse, VisionLatest } from './types'

const STATUS_INTERVAL_MS = 250
const VISION_INTERVAL_MS = 200
const MAX_BACKOFF_MS = 4000
const STALE_VISION_MS = 1000

export interface LiveHandlers {
  onStatus: (s: StatusResponse) => void
  onVision: (v: VisionLatest, stale: boolean) => void
  onConnection: (connected: boolean) => void
}

export class LiveController {
  private statusTimer: ReturnType<typeof setTimeout> | null = null
  private visionTimer: ReturnType<typeof setTimeout> | null = null
  private statusBusy = false
  private visionBusy = false
  private backoff = STATUS_INTERVAL_MS
  private lastStatusSeq = -1
  private lastVisionSeq = -1
  private running = false

  sessionId: string | null = null
  sourceRevision = 1
  visionActive = false

  constructor(
    private api: StrideApi,
    private speech: SpeechController,
    private handlers: LiveHandlers,
  ) {}

  start(sessionId: string, sourceRevision: number) {
    this.sessionId = sessionId
    this.sourceRevision = sourceRevision
    this.running = true
    this.loopStatus()
    this.loopVision()
  }

  stop() {
    this.running = false
    if (this.statusTimer) clearTimeout(this.statusTimer)
    if (this.visionTimer) clearTimeout(this.visionTimer)
    this.statusTimer = this.visionTimer = null
  }

  setVisionActive(active: boolean) {
    this.visionActive = active
  }

  // Adopt a server-advanced revision (e.g. another client switched source).
  adoptRevision(rev: number) {
    if (rev > this.sourceRevision) {
      this.sourceRevision = rev
      this.speech.resetForSource()
    }
  }

  private loopStatus() {
    const tick = async () => {
      await this.pollStatus()
      if (this.running) this.statusTimer = setTimeout(tick, this.backoff)
    }
    tick()
  }

  private loopVision() {
    const tick = async () => {
      await this.pollVision()
      if (this.running) this.visionTimer = setTimeout(tick, VISION_INTERVAL_MS)
    }
    tick()
  }

  private hidden() {
    return typeof document !== 'undefined' && document.hidden
  }

  private async pollStatus() {
    if (this.statusBusy || !this.running || !this.sessionId || this.hidden()) return
    this.statusBusy = true
    try {
      const s = await this.api.status(this.sessionId)
      if (s.state_seq >= this.lastStatusSeq) {
        this.lastStatusSeq = s.state_seq
        if (s.camera?.source_revision != null) this.adoptRevision(s.camera.source_revision)
        this.handlers.onStatus(s)
        if (s.speech_event) this.speech.offer(s.speech_event)
      }
      this.backoff = STATUS_INTERVAL_MS
      this.handlers.onConnection(true)
    } catch {
      this.backoff = Math.min(this.backoff * 2, MAX_BACKOFF_MS)
      this.handlers.onConnection(false)
    } finally {
      this.statusBusy = false
    }
  }

  private async pollVision() {
    if (this.visionBusy || !this.running || !this.visionActive || !this.sessionId || this.hidden()) return
    this.visionBusy = true
    try {
      const v = await this.api.visionLatest(this.sessionId)
      if (v.source_revision != null && v.source_revision < this.sourceRevision) return
      if (v.state_seq != null && v.state_seq < this.lastVisionSeq) return
      if (v.state_seq != null) this.lastVisionSeq = v.state_seq
      const age = v.completed_ms != null ? this.api.clock.ageMs(v.completed_ms) : v.age_ms ?? null
      const stale = v.status !== 'live' || (age != null && age > STALE_VISION_MS)
      this.handlers.onVision(v, stale)
      // Stale results never become speech; the controller also re-checks age.
      if (!stale && v.speech_event) this.speech.offer(v.speech_event)
    } catch {
      /* status poll already reports the down link */
    } finally {
      this.visionBusy = false
    }
  }
}
