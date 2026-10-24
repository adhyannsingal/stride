import { strideApi } from './api.ts'

export type SpeechKind = 'urgent' | 'fault' | 'route' | 'observation' | 'info'
export interface SpokenEvent {
  id: string
  text: string
  kind: SpeechKind
  expiresAt: number // local monotonic deadline, normalized at receipt
  valid: () => boolean // rechecked at playback AND while speaking
}
const priorities: Record<SpeechKind, number> = { urgent: 0, fault: 1, route: 2, observation: 3, info: 4 }
export class SpeechController {
  private enabled = false
  private spoken = new Set<string>()
  private queue: SpokenEvent[] = []
  private current: SpokenEvent | null = null
  private generation = 0
  private timer: ReturnType<typeof setTimeout> | null = null
  rate = 1
  observations = true
  constructor(private now = () => performance.now(), private synth = () => window.speechSynthesis,
    private utterance = (text: string) => new SpeechSynthesisUtterance(text)) {}
  available() { return typeof window !== 'undefined' && 'speechSynthesis' in window }
  enable() { this.enabled = this.available(); return this.enabled }
  status() { return !this.available() ? 'Browser speech unavailable' : this.enabled ? 'Browser speech enabled' : 'Browser speech off' }
  private valid(event: SpokenEvent) {
    return event.expiresAt > this.now() && event.valid() && (event.kind !== 'observation' || this.observations)
  }
  enqueue(event: SpokenEvent) {
    if (!this.enabled || this.spoken.has(event.id) || !this.valid(event)) return
    // At the bounded dedupe limit fail closed until an explicit new session.
    if (this.spoken.size >= 4096) return
    this.spoken.add(event.id)
    if (priorities[event.kind] <= 1) {
      this.queue = this.queue.filter(e => priorities[e.kind] <= priorities[event.kind])
    }
    if (this.current && priorities[event.kind] < priorities[this.current.kind]) this.interrupt()
    this.queue.push(event)
    this.queue.sort((a,b) => priorities[a.kind] - priorities[b.kind])
    this.queue = this.queue.slice(0, 8)
    this.pump()
  }
  // Only for explicit user-requested informational audio; live/route events use enqueue.
  speak(id: string, text: string) {
    this.enqueue({id, text, kind: 'info', expiresAt: this.now() + 5000, valid: () => true})
  }
  private interrupt() {
    ++this.generation // detach callbacks BEFORE calling browser cancel
    this.current = null
    if (this.timer) clearTimeout(this.timer)
    this.timer = null
    if (this.available()) this.synth().cancel()
  }
  reconcile() {
    this.queue = this.queue.filter(e => this.valid(e))
    if (this.current && !this.valid(this.current)) this.interrupt()
    this.pump()
  }
  private pump() {
    if (this.current) return
    let next: SpokenEvent | undefined
    while ((next = this.queue.shift())) {
      if (this.valid(next)) break
    }
    if (!next || !this.valid(next)) return
    this.current = next
    const token = ++this.generation
    const u = this.utterance(next.text)
    u.rate = this.rate
    u.onend = u.onerror = () => {
      if (token !== this.generation) return
      this.current = null
      if (this.timer) clearTimeout(this.timer)
      this.timer = null
      this.pump()
    }
    const check = () => {
      if (token !== this.generation) return
      this.reconcile()
      if (token === this.generation && this.current) this.timer = setTimeout(check, 50)
    }
    this.timer = setTimeout(check, 50)
    this.synth().speak(u)
  }
  cancel() { this.queue = []; this.interrupt() }
  reset() { this.cancel(); this.spoken.clear() }
  pending() { return this.queue.length }
}

/** One request at a time, including across stop/restart; ignores late completions. */
export class PollController {
  private version = 0
  private timer: ReturnType<typeof setTimeout> | null = null
  private abort: AbortController | null = null
  private running: Promise<void> = Promise.resolve()
  start<T>(task: (signal: AbortSignal) => Promise<T>, accept: (value: T, started: number) => void,
    fail: (error: unknown) => void, interval = 200) {
    this.stop()
    const version = this.version
    let errors = 0
    const run = async () => {
      if (version !== this.version) return
      this.abort = new AbortController()
      const started = performance.now()
      try {
        const result = await task(this.abort.signal)
        if (version !== this.version) return
        accept(result, started); errors = 0
      } catch (error) {
        if (version !== this.version) return
        errors++; fail(error)
      }
      if (version === this.version) this.timer = setTimeout(() => { this.running = run() },
        errors ? Math.min(5000, interval * 2 ** errors) : Math.max(0, interval - (performance.now() - started)))
    }
    this.running = this.running.then(run)
  }
  stop() { this.version++; this.abort?.abort(); if (this.timer) clearTimeout(this.timer); this.timer = null }
}

export interface CameraOptions {
  sessionId: string
  role: 'browser' | 'viewer' | 'glasses'
  consent: boolean
  userGesture: boolean
  sourceRevision: number
  singleProducer: boolean
  allowed: () => boolean
  fps?: number
}
export class BrowserCameraController {
  readonly deviceId = `browser-${crypto.randomUUID()}`
  private stream: MediaStream | null = null
  private timer: ReturnType<typeof setTimeout> | null = null
  private abort: AbortController | null = null
  private generation = 0
  private pending: Promise<unknown> = Promise.resolve()
  private video: HTMLVideoElement | null = null
  constructor(private upload = strideApi.uploadFrame) {}
  async start(video: HTMLVideoElement, options: CameraOptions, onError: (message: string) => void) {
    this.stop()
    if (!options.userGesture || !options.consent || options.role !== 'browser' || !options.singleProducer || !options.allowed()) {
      throw new Error('Browser capture requires an explicit Start, consent, and a single-producer development session.')
    }
    if (!Number.isInteger(options.sourceRevision) || options.sourceRevision < 0) throw new Error('Server source revision is unavailable.')
    const generation = this.generation
    const allowed = () => generation === this.generation && options.allowed()
    await this.pending.catch(() => {})
    if (!allowed()) return
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera unavailable. Use HTTPS or localhost and allow camera permission.')
    let stream: MediaStream
    try { stream = await navigator.mediaDevices.getUserMedia({video: {facingMode: 'environment', width: {ideal: 640}, height: {ideal: 480}}, audio: false}) }
    catch (error) { throw new Error(error instanceof DOMException && error.name === 'NotAllowedError' ? 'Camera permission denied. Enable it in browser settings, then explicitly try again.' : 'Camera unavailable or already in use.') }
    if (!allowed()) { stream.getTracks().forEach(t => t.stop()); return }
    this.stream = stream; this.video = video; video.srcObject = stream
    try { await video.play() } catch { this.stop(); throw new Error('Camera preview could not start.') }
    if (!allowed()) return
    const canvas = document.createElement('canvas')
    const bootId = crypto.randomUUID()
    let sequence = 0
    const period = 1000 / Math.max(1, Math.min(5, options.fps || 5))
    const send = async () => {
      if (!allowed()) return
      const began = performance.now()
      try {
        if (video.readyState >= 2 && video.videoWidth && video.videoHeight) {
          const scale = Math.min(1, 640 / Math.max(video.videoWidth, video.videoHeight))
          canvas.width = Math.round(video.videoWidth * scale); canvas.height = Math.round(video.videoHeight * scale)
          const captured = Date.now()
          canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height)
          const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.78))
          if (!allowed()) return
          if (!blob || blob.size > 524288) throw new Error('Camera JPEG exceeds the 512 KiB limit or could not be encoded.')
          const form = new FormData()
          form.append('file', blob, 'frame.jpg')
          const fields = {session_id: options.sessionId, device_id: this.deviceId, boot_id: bootId,
            frame_id: crypto.randomUUID(), sequence: ++sequence, captured_ms: captured,
            source: 'real', origin: 'browser_camera', source_revision: options.sourceRevision}
          for (const [key, value] of Object.entries(fields)) form.append(key, String(value))
          this.abort = new AbortController()
          await this.upload(form, this.abort.signal)
          if (!allowed()) return
        }
      } catch (error) {
        if (allowed()) { this.stop(); onError(error instanceof Error ? error.message : 'Camera upload failed. Explicitly restart after checking the connection.'); throw error }
        return
      }
      if (allowed()) this.timer = setTimeout(() => { this.pending = send().catch(() => {}) }, Math.max(0, period - (performance.now() - began)))
    }
    this.pending = send()
    await this.pending
  }
  stop() {
    ++this.generation
    if (this.timer) clearTimeout(this.timer)
    this.timer = null; this.abort?.abort()
    this.stream?.getTracks().forEach(track => track.stop()); this.stream = null
    if (this.video) this.video.srcObject = null
    this.video = null
  }
}
