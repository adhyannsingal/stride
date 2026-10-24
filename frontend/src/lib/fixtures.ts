// STRIDE frontend — explicit development fixtures (TypeScript).
//
// SELECTABLE development mode only. Never a silent fallback. Every shape mirrors
// contracts/API.md / examples.json. The UI labels this mode as "Simulation"
// wherever it is active.

import type {
  MemoryRecord,
  RouteActionName,
  RouteDefinition,
  SessionResponse,
  StatusResponse,
  VisionActionName,
  VisionLatest,
  VisionStatus,
} from './types'

const DEMO_ROUTE_ID = '00000000-0000-4000-8000-000000000050'

const DEMO_ROUTE: RouteDefinition = {
  route_id: DEMO_ROUTE_ID,
  name: 'Station entrance → Library desk',
  is_demo: true,
  steps: [
    { checkpoint_id: 'A', instruction: 'At the marked start, turn left toward checkpoint B.', pattern: 'left' },
    { checkpoint_id: 'B', instruction: 'At checkpoint B, turn right toward checkpoint C.', pattern: 'right' },
    { checkpoint_id: 'C', instruction: 'Checkpoint C reached. Route complete.', pattern: 'stop' },
  ],
  return_steps: [],
}

export class Fixtures {
  private seq = 40
  private sourceRevision = 1
  private route: { state: StatusResponse['route']['state']; index: number } = { state: 'idle', index: 0 }
  private routeId: string | null = null
  private vision: VisionStatus = 'paused'
  private frameCounter = 0

  private next() {
    return ++this.seq
  }
  private now() {
    return Date.now()
  }

  time() {
    return { server_ms: this.now() }
  }
  health() {
    return { status: 'ok', version: 'fixture', commit: 'fixture', provider_configured: true }
  }
  auth(code: string) {
    if (!code) throw Object.assign(new Error('Enter the access code.'), { status: 401 })
    return { authenticated: true }
  }

  createSession(mode: string, cameraOrigin: string): SessionResponse {
    return {
      session_id: '00000000-0000-4000-8000-000000000010',
      mode,
      source: 'fixture',
      origin: cameraOrigin as any,
      source_revision: this.sourceRevision,
      state_seq: this.next(),
      server_time_ms: this.now(),
    }
  }

  selectCamera(cameraOrigin: string): SessionResponse {
    this.sourceRevision += 1
    this.vision = 'paused'
    return {
      session_id: '00000000-0000-4000-8000-000000000010',
      mode: 'training',
      source: 'fixture',
      origin: cameraOrigin as any,
      source_revision: this.sourceRevision,
      state_seq: this.next(),
      server_time_ms: this.now(),
    }
  }

  listRoutes() {
    return { routes: [DEMO_ROUTE] }
  }

  routeAction(action: RouteActionName, routeId?: string): StatusResponse {
    const steps = DEMO_ROUTE.steps
    switch (action) {
      case 'start':
        this.routeId = routeId || DEMO_ROUTE_ID
        this.route = { state: 'guiding', index: 0 }
        break
      case 'confirm':
        if (this.route.state === 'guiding') {
          if (this.route.index >= steps.length - 1) this.route = { state: 'completed', index: steps.length - 1 }
          else this.route.index += 1
        }
        break
      case 'repeat':
        break
      case 'pause':
        if (this.route.state === 'guiding') this.route.state = 'paused'
        break
      case 'resume':
        if (this.route.state === 'paused') this.route.state = 'guiding'
        break
      case 'stop':
        this.route = { state: 'idle', index: 0 }
        this.routeId = null
        break
    }
    return this.status('00000000-0000-4000-8000-000000000010', action)
  }

  status(sessionId: string, lastAction?: RouteActionName): StatusResponse {
    const steps = DEMO_ROUTE.steps
    const idx = Math.min(this.route.index, steps.length - 1)
    const step = steps[idx]
    const active = this.route.state !== 'idle'
    const emitSpeech =
      active && (lastAction === 'start' || lastAction === 'confirm' || lastAction === 'repeat' || lastAction === 'resume')
    return {
      session_id: sessionId,
      state_seq: this.next(),
      server_time_ms: this.now(),
      mode: 'training',
      route: {
        route_id: active ? this.routeId || DEMO_ROUTE_ID : null,
        state: this.route.state,
        checkpoint_index: active ? idx : null,
        checkpoint_id: active ? step.checkpoint_id : null,
        instruction: active ? step.instruction : null,
        pattern: active ? step.pattern : 'none',
        overlay: 'none',
      },
      camera: {
        origin: 'browser_camera',
        source: 'fixture',
        connected: true,
        age_ms: 200,
        source_revision: this.sourceRevision,
      },
      feedback: {
        origin: 'simulator',
        source: 'simulated',
        connected: true,
        valid: true,
        distance_cm: 120,
        age_ms: 100,
        alert: 'none',
        ack_state: 'unavailable',
      },
      perception: { provider: 'fixture', available: true, busy: false, latest: null },
      vision: { status: this.vision, age_ms: this.vision === 'live' ? 250 : null, result_hz: this.vision === 'live' ? 5 : 0 },
      speech_event: emitSpeech
        ? {
            event_id: 'evt-route-' + this.next(),
            kind: 'route',
            priority: 'route',
            text: step.instruction,
            created_ms: this.now(),
            expires_ms: this.now() + 8000,
          }
        : null,
      haptic_event: null,
      memory: { durability: 'local_sqlite', export_available: true },
    }
  }

  uploadFrame(frameId: string, capturedMs: number) {
    this.frameCounter += 1
    return {
      frame_id: frameId,
      origin: 'browser_camera',
      source: 'fixture',
      source_revision: this.sourceRevision,
      captured_ms: capturedMs,
      received_ms: this.now(),
      clock_synced: true,
      width: 640,
      height: 480,
      server_time_ms: this.now(),
    }
  }

  visionControl(action: VisionActionName) {
    if (action === 'start' || action === 'resume') this.vision = 'live'
    else this.vision = 'paused'
    return {
      session_id: '00000000-0000-4000-8000-000000000010',
      status: this.vision,
      source_revision: this.sourceRevision,
      state_seq: this.next(),
      server_time_ms: this.now(),
    }
  }

  visionLatest(sessionId: string): VisionLatest {
    const now = this.now()
    if (this.vision !== 'live') {
      return {
        session_id: sessionId,
        state_seq: this.next(),
        server_time_ms: now,
        status: this.vision,
        source_revision: this.sourceRevision,
        origin: 'browser_camera',
        source: 'fixture',
        provider: 'yolo',
        result_hz: 0,
        objects: [],
        speech_event: null,
      }
    }
    this.frameCounter += 1
    const completedMs = now - 50
    const speechEvent =
      this.frameCounter % 15 === 0
        ? {
            event_id: 'evt-vision-' + this.frameCounter,
            kind: 'observation',
            priority: 'observation' as const,
            text: 'Chair on the left.',
            created_ms: now,
            expires_ms: now + 1000,
          }
        : null
    return {
      session_id: sessionId,
      state_seq: this.next(),
      server_time_ms: now,
      frame_id: 'frame-' + this.frameCounter,
      captured_ms: now - 150,
      completed_ms: completedMs,
      age_ms: now - completedMs,
      source_revision: this.sourceRevision,
      origin: 'browser_camera',
      source: 'fixture',
      status: 'live',
      provider: 'yolo',
      result_hz: 5,
      objects: [{ track_id: 'track-1', label: 'chair', score: 0.83, box: [0.1, 0.2, 0.4, 0.9], position: 'left' }],
      speech_event: speechEvent,
    }
  }

  perception(frameId: string, task: string, target?: string) {
    const found = task !== 'find' || (!!target && /chair|mug|door|bench/i.test(target))
    return {
      observation_id: 'obs-' + this.next(),
      status: found ? 'ok' : 'not_found',
      origin: 'browser_camera',
      source: 'fixture',
      provider: 'fixture',
      frame_id: frameId,
      source_revision: this.sourceRevision,
      captured_ms: this.now() - 200,
      completed_ms: this.now(),
      age_ms: 200,
      latency_ms: 180,
      objects: found ? [{ label: target || 'chair', box: [0.35, 0.1, 0.7, 0.85], position: 'center' }] : [],
      speakable: found,
      speech_event: found
        ? {
            event_id: 'evt-perc-' + this.next(),
            kind: 'observation',
            priority: 'observation' as const,
            text: (target || 'chair') + ' in the center of view.',
            created_ms: this.now(),
            expires_ms: this.now() + 5000,
          }
        : null,
    }
  }

  memory(kind: string): { records: MemoryRecord[] } {
    if (kind === 'routes') return { records: [] }
    return {
      records: [
        { kind: 'sighting', label: 'chair', source: 'fixture', age_ms: 42000, checkpoint_id: 'A', captured_ms: this.now() - 42000 },
      ],
    }
  }
}
