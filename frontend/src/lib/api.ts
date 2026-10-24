// STRIDE frontend — single API adapter (TypeScript).
//
// Every backend call goes through this module. Fixtures are an EXPLICIT,
// intentionally-selected development mode, never a silent fallback after a real
// error. On a real-mode failure the error propagates to the UI; we never fake
// success or substitute a fixture.

import { Fixtures } from './fixtures'
import type {
  MemoryRecord,
  RouteActionName,
  RouteDefinition,
  SessionResponse,
  StatusResponse,
  VisionActionName,
  VisionLatest,
} from './types'

export type ApiMode = 'real' | 'fixture'

export class ApiError extends Error {
  status?: number
  code?: string
  retryable?: boolean
  constructor(message: string, info: Partial<ApiError> = {}) {
    super(message)
    this.name = 'ApiError'
    Object.assign(this, info)
  }
}

class Clock {
  offsetMs = 0
  rttMs: number | null = null
  synced = false
  align(serverMs: number, t0: number, t1: number) {
    const rtt = Math.max(0, t1 - t0)
    this.rttMs = rtt
    this.offsetMs = serverMs - (t0 + rtt / 2)
    this.synced = true
    return this.offsetMs
  }
  serverNow() {
    return this.synced ? Date.now() + this.offsetMs : Date.now()
  }
  ageMs(serverStampMs: number | undefined | null): number | null {
    if (!this.synced || serverStampMs == null) return null
    return Math.max(0, this.serverNow() - serverStampMs)
  }
}

function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export class StrideApi {
  mode: ApiMode
  baseUrl: string
  clock = new Clock()
  private fixtures = new Fixtures()

  constructor(opts: { mode?: ApiMode; baseUrl?: string } = {}) {
    this.mode = opts.mode ?? 'fixture'
    this.baseUrl = (opts.baseUrl ?? '').replace(/\/$/, '')
  }

  get isFixture() {
    return this.mode === 'fixture'
  }
  setMode(mode: ApiMode) {
    this.mode = mode
  }

  private async req<T>(
    path: string,
    init: RequestInit & { raw?: boolean } = {},
  ): Promise<T> {
    const res = await fetch(this.baseUrl + path, {
      ...init,
      credentials: 'same-origin',
      cache: 'no-store',
    })
    const text = await res.text()
    let payload: any = null
    if (text) {
      try {
        payload = JSON.parse(text)
      } catch {
        payload = { error: { code: 'bad_json', message: text.slice(0, 200) } }
      }
    }
    if (!res.ok) {
      throw new ApiError(payload?.error?.message || `HTTP ${res.status}`, {
        status: res.status,
        code: payload?.error?.code,
        retryable: payload?.error?.retryable ?? false,
      })
    }
    return payload as T
  }

  async syncClock() {
    if (this.isFixture) {
      const t = this.fixtures.time()
      this.clock.align(t.server_ms, Date.now(), Date.now())
      return
    }
    const t0 = Date.now()
    const p = await this.req<{ server_ms?: number; server_time_ms?: number }>('/time')
    const t1 = Date.now()
    this.clock.align(p.server_ms ?? p.server_time_ms ?? Date.now(), t0, t1)
  }

  async health() {
    if (this.isFixture) return this.fixtures.health()
    return this.req<any>('/health')
  }

  async auth(accessCode: string) {
    if (this.isFixture) return this.fixtures.auth(accessCode)
    return this.req<{ authenticated: boolean }>('/auth', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_code: accessCode }),
    })
  }

  async createSession(mode = 'training', cameraOrigin = 'browser_camera') {
    if (this.isFixture) return this.fixtures.createSession(mode, cameraOrigin)
    return this.req<SessionResponse>('/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_id: uuid(), mode, camera_origin: cameraOrigin }),
    })
  }

  async selectCamera(sessionId: string, cameraOrigin: string, cameraDeviceId?: string) {
    if (this.isFixture) return this.fixtures.selectCamera(cameraOrigin)
    return this.req<SessionResponse>(`/sessions/${sessionId}/camera`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action_id: uuid(),
        camera_origin: cameraOrigin,
        camera_device_id: cameraDeviceId,
      }),
    })
  }

  async listRoutes(): Promise<{ routes: RouteDefinition[] }> {
    if (this.isFixture) return this.fixtures.listRoutes()
    return this.req('/routes')
  }

  async routeAction(sessionId: string, action: RouteActionName, routeId?: string) {
    if (this.isFixture) return this.fixtures.routeAction(action, routeId)
    return this.req<any>('/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_id: uuid(), session_id: sessionId, action, route_id: routeId }),
    })
  }

  async status(sessionId: string): Promise<StatusResponse> {
    if (this.isFixture) return this.fixtures.status(sessionId)
    return this.req(`/status?session_id=${encodeURIComponent(sessionId)}`)
  }

  async uploadFrame(args: {
    sessionId: string
    deviceId: string
    bootId: string
    frameId: string
    sequence: number
    capturedMs: number
    sourceRevision: number
    blob: Blob
    signal?: AbortSignal
  }) {
    if (this.isFixture) return this.fixtures.uploadFrame(args.frameId, args.capturedMs)
    return this.req<any>('/frame', {
      method: 'POST',
      headers: {
        'Content-Type': 'image/jpeg',
        'X-Session-Id': args.sessionId,
        'X-Device-Id': args.deviceId,
        'X-Boot-Id': args.bootId,
        'X-Frame-Id': args.frameId,
        'X-Sequence': String(args.sequence),
        'X-Captured-Ms': String(args.capturedMs),
        'X-Clock-Synced': String(this.clock.synced),
        'X-Source-Revision': String(args.sourceRevision),
      },
      body: args.blob,
      signal: args.signal,
    })
  }

  async visionControl(sessionId: string, action: VisionActionName) {
    if (this.isFixture) return this.fixtures.visionControl(action)
    return this.req<any>('/vision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_id: uuid(), session_id: sessionId, action }),
    })
  }

  async visionLatest(sessionId: string, signal?: AbortSignal): Promise<VisionLatest> {
    if (this.isFixture) return this.fixtures.visionLatest(sessionId)
    return this.req(`/vision/latest?session_id=${encodeURIComponent(sessionId)}`, { signal })
  }

  async perception(sessionId: string, frameId: string, task: string, target?: string) {
    if (this.isFixture) return this.fixtures.perception(frameId, task, target)
    return this.req<any>('/perception', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_id: uuid(), session_id: sessionId, frame_id: frameId, task, target }),
    })
  }

  async memory(sessionId: string, kind = 'sightings', limit = 20): Promise<{ records: MemoryRecord[] }> {
    if (this.isFixture) return this.fixtures.memory(kind)
    return this.req(`/memory?session_id=${encodeURIComponent(sessionId)}&kind=${kind}&limit=${limit}`)
  }
}

export { uuid }
