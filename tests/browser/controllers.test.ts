// Controller logic tests for the STRIDE React frontend.
// Run: node --experimental-strip-types tests/browser/controllers.test.ts
//
// No test framework — uses node:assert so it runs against the real TS source
// via Node's native type stripping (Node 22+/25). Covers fixtures route/vision
// state machines and the speech controller (dedupe/priority/expiry/stale).

import assert from 'node:assert/strict'
import { Fixtures } from '../../frontend/src/lib/fixtures.ts'
import { SpeechController, PRIORITY } from '../../frontend/src/lib/speech.ts'
import type { SpeechEvent } from '../../frontend/src/lib/types.ts'

const clock = {
  serverNow: () => Date.now(),
  ageMs: (ms?: number | null) => (ms == null ? null : Math.max(0, Date.now() - ms)),
}

function evt(id: string, priority: SpeechEvent['priority'], over: Partial<SpeechEvent> = {}): SpeechEvent {
  const now = Date.now()
  return { event_id: id, kind: priority, priority, text: id, created_ms: now, expires_ms: now + 5000, ...over }
}

let passed = 0
async function test(name: string, fn: () => void | Promise<void>) {
  try {
    await fn()
    passed += 1
    console.log('  ok -', name)
  } catch (err) {
    console.error('  FAIL -', name, '\n   ', (err as Error).message)
    process.exitCode = 1
  }
}

// browser stubs for speech
;(globalThis as any).window = {
  speechSynthesis: { speak: (u: any) => queueMicrotask(() => u.onend?.()), cancel: () => {} },
}
;(globalThis as any).SpeechSynthesisUtterance = class {
  text: string
  rate = 1
  onend: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(t: string) {
    this.text = t
  }
}

await test('route start -> guiding @0 with speech event', () => {
  const f = new Fixtures()
  const r = f.routeAction('start', 'r')
  assert.equal(r.route.state, 'guiding')
  assert.equal(r.route.checkpoint_index, 0)
  assert.ok(r.speech_event)
})

await test('confirm advances; repeat does not', () => {
  const f = new Fixtures()
  f.routeAction('start', 'r')
  assert.equal(f.routeAction('confirm').route.checkpoint_index, 1)
  assert.equal(f.routeAction('repeat').route.checkpoint_index, 1)
})

await test('final confirm completes once, no overflow', () => {
  const f = new Fixtures()
  f.routeAction('start', 'r')
  f.routeAction('confirm')
  f.routeAction('confirm')
  assert.equal(f.routeAction('confirm').route.state, 'completed')
  const again = f.routeAction('confirm')
  assert.equal(again.route.state, 'completed')
  assert.equal(again.route.checkpoint_index, 2)
})

await test('pause/resume/stop transitions', () => {
  const f = new Fixtures()
  f.routeAction('start', 'r')
  assert.equal(f.routeAction('pause').route.state, 'paused')
  assert.equal(f.routeAction('resume').route.state, 'guiding')
  const s = f.routeAction('stop')
  assert.equal(s.route.state, 'idle')
  assert.equal(s.route.checkpoint_index, null)
})

await test('vision paused until start, live after', () => {
  const f = new Fixtures()
  assert.equal(f.visionLatest('s').status, 'paused')
  f.visionControl('start')
  assert.equal(f.visionLatest('s').status, 'live')
})

await test('camera selection bumps source_revision and clears results', () => {
  const f = new Fixtures()
  f.visionControl('start')
  const before = f.visionLatest('s').source_revision
  f.selectCamera('browser_camera')
  const after = f.visionLatest('s')
  assert.equal(after.source_revision, before + 1)
  assert.equal(after.status, 'paused')
})

await test('live box canonical xyxy min<max 0..1', () => {
  const f = new Fixtures()
  f.visionControl('start')
  const [x1, y1, x2, y2] = f.visionLatest('s').objects[0].box
  assert.ok(x1 < x2 && y1 < y2)
  assert.ok([x1, y1, x2, y2].every((n) => n >= 0 && n <= 1))
})

await test('speech dedupes by event_id', () => {
  const s = new SpeechController(clock as any)
  s.enable()
  assert.equal(s.offer(evt('e1', 'route')), true)
  assert.equal(s.offer(evt('e1', 'route')), false)
})

await test('expired event dropped and blocked from replay', () => {
  const s = new SpeechController(clock as any)
  s.enable()
  const now = Date.now()
  assert.equal(s.offer(evt('ex', 'route', { created_ms: now - 10000, expires_ms: now - 1 })), false)
  assert.equal(s.offer(evt('ex', 'route')), false)
})

await test('priority order urgent>fault>route>observation', () => {
  assert.ok(PRIORITY.urgent > PRIORITY.fault)
  assert.ok(PRIORITY.fault > PRIORITY.route)
  assert.ok(PRIORITY.route > PRIORITY.observation)
})

await test('stale live observation (age>1000ms) unspeakable', () => {
  const s = new SpeechController(clock as any)
  s.enable()
  const now = Date.now()
  assert.equal(s.offer(evt('o1', 'observation', { created_ms: now - 1500, age_ms: 1500 })), false)
})

await test('resetForSource clears consumed ids', () => {
  const s = new SpeechController(clock as any)
  s.enable()
  s.offer(evt('e2', 'route'))
  s.resetForSource()
  assert.equal(s.offer(evt('e2', 'route')), true)
})

console.log(`\n${passed} checks passed.`)
