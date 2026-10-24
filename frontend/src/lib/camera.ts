// STRIDE frontend — camera controller (TypeScript).
//
// Browser camera capture + upload loop. Rules:
//  * NEVER getUserMedia on load. Only after an explicit gesture.
//  * Consent is required for EVERY upload. Without consent, no frame leaves the
//    device. Revoking consent stops uploads immediately and bumps the generation
//    so in-flight/late results are invalidated.
//  * 640x480, one request in flight, drop obsolete captures.
//  * Captured pixels are unmirrored.
//  * Glasses (W11) mode never activates the phone camera: the loop is simply not
//    started for that origin; results are consumed from the backend instead.

import type { StrideApi } from './api'

const TARGET_HZ = 5
const MIN_INTERVAL_MS = 1000 / TARGET_HZ

export interface CameraContext {
  sessionId: string
  deviceId: string
  sourceRevision: number
  consent: boolean
}

export class CameraController {
  stream: MediaStream | null = null
  running = false
  private inFlight = false
  private sequence = 0
  private generation = 0
  private bootId = 'boot-' + Math.random().toString(16).slice(2, 10)
  private timer: ReturnType<typeof setTimeout> | null = null
  private canvas = document.createElement('canvas')

  constructor(
    private api: StrideApi,
    private video: HTMLVideoElement,
    private getContext: () => CameraContext,
    private onError: (e: Error) => void = () => {},
  ) {
    this.canvas.width = 640
    this.canvas.height = 480
  }

  get active() {
    return this.running && !!this.stream
  }

  async enableProducer(deviceId?: string) {
    const video: MediaTrackConstraints = deviceId
      ? { deviceId: { exact: deviceId }, width: { ideal: 640 }, height: { ideal: 480 } }
      : { facingMode: { ideal: 'environment' }, width: { ideal: 640 }, height: { ideal: 480 } }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video })
    this.stream = stream
    this.video.srcObject = stream
    await this.video.play()
    const track = stream.getVideoTracks()[0]
    const settings = track?.getSettings?.() ?? {}
    return { deviceId: settings.deviceId ?? deviceId ?? null, label: track?.label ?? '' }
  }

  async listVideoDevices(): Promise<MediaDeviceInfo[]> {
    if (!navigator.mediaDevices?.enumerateDevices) return []
    const all = await navigator.mediaDevices.enumerateDevices()
    return all.filter((d) => d.kind === 'videoinput')
  }

  start() {
    if (!this.stream) throw new Error('Enable the camera producer first.')
    this.running = true
    this.generation += 1
    this.schedule(0)
  }

  pause() {
    this.running = false
    this.generation += 1 // invalidate late responses
    if (this.timer) clearTimeout(this.timer)
    this.timer = null
  }

  stop() {
    this.pause()
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop())
      this.stream = null
    }
    this.video.srcObject = null
    this.inFlight = false
  }

  // Called on consent revocation: stop uploading and invalidate pending output.
  revokeConsent() {
    this.generation += 1
    this.running = false
    if (this.timer) clearTimeout(this.timer)
    this.timer = null
  }

  private schedule(delay: number) {
    if (!this.running) return
    this.timer = setTimeout(() => void this.tick(), delay)
  }

  private async tick() {
    if (!this.running) return
    const ctx = this.getContext()
    // Consent gate: without consent, do not capture or upload. Keep polling the
    // gate cheaply so re-consent resumes without a restart.
    if (!ctx.consent || !ctx.sessionId) {
      this.schedule(MIN_INTERVAL_MS)
      return
    }
    if (this.inFlight) {
      this.schedule(MIN_INTERVAL_MS)
      return
    }
    const gen = this.generation
    const t0 = performance.now()
    let blob: Blob
    try {
      blob = await this.capture()
    } catch (e) {
      this.onError(e as Error)
      this.schedule(MIN_INTERVAL_MS)
      return
    }
    if (gen !== this.generation || !this.running) return
    this.inFlight = true
    this.sequence += 1
    const frameId = 'frame-' + this.bootId + '-' + this.sequence
    try {
      await this.api.uploadFrame({
        sessionId: ctx.sessionId,
        deviceId: ctx.deviceId,
        bootId: this.bootId,
        frameId,
        sequence: this.sequence,
        capturedMs: this.api.clock.serverNow(),
        sourceRevision: ctx.sourceRevision,
        blob,
      })
    } catch (e) {
      if (gen === this.generation) this.onError(e as Error)
    } finally {
      this.inFlight = false
      const elapsed = performance.now() - t0
      this.schedule(Math.max(0, MIN_INTERVAL_MS - elapsed))
    }
  }

  private capture(): Promise<Blob> {
    const v = this.video
    if (!v.videoWidth) return Promise.reject(new Error('Camera has no frame yet.'))
    const g = this.canvas.getContext('2d')!
    g.setTransform(1, 0, 0, 1, 0, 0) // unmirrored captured pixels
    g.drawImage(v, 0, 0, this.canvas.width, this.canvas.height)
    return new Promise((resolve, reject) =>
      this.canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('JPEG encode failed'))), 'image/jpeg', 0.8),
    )
  }
}
