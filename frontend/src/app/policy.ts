import type { DeviceStatus, NavigationProgress, ObstacleState, VisionLatest } from './api.ts'
import type { SpokenEvent } from './controllers.ts'

export const freshVision = (v: VisionLatest | null, received: number, now = performance.now()) =>
  !!v && v.state === 'active' && v.status === 'live' && v.age_ms !== null && Number.isFinite(v.age_ms) && v.age_ms >= 0 && v.age_ms + Math.max(0, now - received) <= 1000
export const newerVision = (old: VisionLatest | null, next: VisionLatest) => !old ||
  (next.generation >= old.generation && next.state_seq >= old.state_seq && next.source_revision >= old.source_revision &&
   (next.delivered_ms === undefined || old.delivered_ms === undefined || next.delivered_ms >= old.delivered_ms))
export const visionActionAllowed = (state: VisionLatest['state'], action: string) =>
  ({idle: ['start'], active: ['pause','stop'], paused: ['resume','stop'], stopped: []}[state] as string[]).includes(action)
export function obstacleState(nav: NavigationProgress | null, device: DeviceStatus | null, deviceFresh: boolean, deviceExpected: boolean): ObstacleState | null {
  const readings: ObstacleState[] = []
  if (nav?.obstacle_state) readings.push(nav.obstacle_state)
  if (deviceExpected) readings.push(deviceFresh && device?.measurement_fresh && device.sensor_valid ? device.obstacle_state : 'unknown')
  return (['danger','caution','unknown','clear'] as ObstacleState[]).find(s => readings.includes(s)) || null
}
export function routeSpeech(session: string, nav: NavigationProgress, deadline: number, valid: () => boolean): SpokenEvent | null {
  const e = nav.guidance_event
  return e?.valid && nav.state === 'guiding' && e.navigation_id === nav.navigation_id && e.state_revision === nav.state_revision ?
    {id: `${session}:${e.event_id}`, text: e.instruction, kind: 'route', expiresAt: deadline, valid} : null
}
export function visionSpeech(session: string, v: VisionLatest, received: number, valid: () => boolean): SpokenEvent | null {
  const e = v.speech_event
  // Missing capture alignment cannot establish capture-to-speech freshness remotely.
  if (!e || !v.camera_clock_aligned || v.freshness_basis !== 'aligned_capture' || !freshVision(v, received) || e.generation !== v.generation || e.source_revision !== v.source_revision) return null
  return {id: `${session}:${e.event_id}`, text: e.text, kind: 'observation', expiresAt: received + 1000 - v.age_ms!, valid}
}
/** An uncertain mutation retains its original ID AND original payload until resolved. */
export class PendingAction<T> {
  value: {id: string; payload: T} | null = null
  begin(payload: T) { return this.value ||= {id: crypto.randomUUID(), payload} }
  clear() { this.value = null }
}
