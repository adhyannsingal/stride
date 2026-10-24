// STRIDE frontend — speech controller (TypeScript).
//
// Plays backend-authorized SpeechEvents. Does NOT synthesize speech from raw
// detection boxes. Rules:
//  * Dedupe by event_id across all poll sources within a session.
//  * Priority: urgent/obstacle/stop > fault > route > observation. A higher
//    priority event cancels the current lower-priority utterance (obstacle/fault
//    interrupt routine speech).
//  * Keep our own bounded queue because speechSynthesis.cancel() clears the
//    browser queue.
//  * Recheck expiry/age at playback. Live observation age > 1000 ms is unspeakable.
//  * OFF until an explicit user gesture (enable/test).
//  * We report BROWSER SPEECH readiness only. We never claim a specific output
//    device (e.g. AirPods) is connected — the web app cannot verify the iOS
//    audio route.

import type { SpeechEvent } from './types'

export const PRIORITY: Record<string, number> = {
  urgent: 4,
  obstacle: 4,
  stop: 4,
  fault: 3,
  route: 2,
  observation: 1,
}

const LIVE_UNSPEAKABLE_AGE_MS = 1000
const MAX_QUEUE = 8

export type SpeechState = 'off' | 'ready' | 'speaking'

interface ClockLike {
  serverNow(): number
  ageMs(ms: number | undefined | null): number | null
}

export class SpeechController {
  enabled = false
  readonly supported =
    typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window
  private consumed = new Set<string>()
  private queue: { event: SpeechEvent; rank: number }[] = []
  private current: { event: SpeechEvent; rank: number } | null = null
  private speaking = false
  private rate = 1

  private clock: ClockLike
  private onState: (s: SpeechState, event?: SpeechEvent | null) => void

  constructor(clock: ClockLike, onState: (s: SpeechState, event?: SpeechEvent | null) => void = () => {}) {
    this.clock = clock
    this.onState = onState
  }

  setRate(rate: number) {
    this.rate = rate
  }

  private rank(e: SpeechEvent) {
    return PRIORITY[e.priority] ?? PRIORITY[e.kind] ?? 0
  }

  enable() {
    this.enabled = true
    if (this.supported) {
      try {
        const u = new SpeechSynthesisUtterance('Speech enabled.')
        u.rate = this.rate
        window.speechSynthesis.speak(u)
      } catch {
        /* ignore */
      }
    }
    this.onState('ready')
  }

  disable() {
    this.enabled = false
    this.clear()
    this.onState('off')
  }

  offer(event: SpeechEvent | null | undefined): boolean {
    if (!event || !event.event_id) return false
    if (this.consumed.has(event.event_id)) return false
    if (!this.fresh(event)) {
      this.consumed.add(event.event_id) // block replay of an expired event
      return false
    }
    this.consumed.add(event.event_id)
    const rank = this.rank(event)
    if (this.current && rank > this.rank(this.current.event)) this.cancelCurrent()
    this.queue.push({ event, rank })
    this.queue.sort((a, b) => b.rank - a.rank)
    if (this.queue.length > MAX_QUEUE) this.queue.length = MAX_QUEUE
    this.drive()
    return true
  }

  private fresh(e: SpeechEvent): boolean {
    const serverNow = this.clock.serverNow()
    if (e.expires_ms != null && serverNow >= e.expires_ms) return false
    if (e.kind === 'observation' || e.priority === 'observation') {
      const age = e.age_ms != null ? e.age_ms : this.clock.ageMs(e.created_ms)
      if (age != null && age > LIVE_UNSPEAKABLE_AGE_MS) return false
    }
    return true
  }

  private drive() {
    if (!this.enabled || !this.supported || this.speaking) return
    while (this.queue.length) {
      const next = this.queue.shift()!
      if (!this.fresh(next.event)) continue
      this.speak(next)
      return
    }
  }

  private speak(item: { event: SpeechEvent; rank: number }) {
    this.current = item
    this.speaking = true
    this.onState('speaking', item.event)
    const u = new SpeechSynthesisUtterance(item.event.text || '')
    u.rate = this.rate
    const done = () => {
      this.speaking = false
      this.current = null
      this.onState('ready')
      this.drive()
    }
    u.onend = done
    u.onerror = done
    try {
      window.speechSynthesis.speak(u)
    } catch {
      done()
    }
  }

  private cancelCurrent() {
    if (this.supported) window.speechSynthesis.cancel()
    this.speaking = false
    this.current = null
  }

  clear() {
    this.queue = []
    this.cancelCurrent()
    this.onState(this.enabled ? 'ready' : 'off')
  }

  resetForSource() {
    this.clear()
    this.consumed.clear()
  }
}
