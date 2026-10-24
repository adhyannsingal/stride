// Behavioral tests of Agent 2's actual speech controller, with mocked audio.
// STRIDE_SPEECH_MODULE selects a checkout/copy; this never proves audible output.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { pathToFileURL } from 'node:url'
import path from 'node:path'
const target=process.env.STRIDE_SPEECH_MODULE || 'frontend/src/lib/speech.ts'
const { SpeechController }=await import(pathToFileURL(path.resolve(target)).href)

function harness({ unknownClock=false, cancelCallback=false }={}) {
  let now=10000
  const spoken=[]
  class Utterance { constructor(text) { this.text=text } }
  globalThis.SpeechSynthesisUtterance=Utterance
  globalThis.window={ SpeechSynthesisUtterance:Utterance,speechSynthesis:{
    speak(utterance) { spoken.push(utterance) },
    cancel() {
      const old=spoken.at(-1)
      if(cancelCallback && old?.onend) queueMicrotask(()=>old.onend())
    },
  }}
  const clock={serverNow:()=>now,ageMs:stamp=>unknownClock?null:now-stamp,monotonicNow:()=>now}
  const controller=new SpeechController(clock)
  controller.enable(); spoken.length=0
  const event=(id,kind,extra={})=>({event_id:id,kind,priority:kind,text:id,created_ms:10000,...extra})
  return { controller,spoken,event,advance(ms) { now+=ms } }
}

test('queued observation age increases before playback',()=>{
  const h=harness()
  h.controller.offer(h.event('route','route'))
  h.controller.offer(h.event('expired-chair','observation',{age_ms:10}))
  h.advance(1200); h.spoken[0].onend()
  assert.equal(h.spoken.some(x=>x.text==='expired-chair'),false)
})

test('unknown observation age fails closed',()=>{
  const h=harness({unknownClock:true})
  assert.equal(h.controller.offer(h.event('unknown-chair','observation')),false)
  assert.equal(h.spoken.length,0)
})

test('late cancelled utterance callback cannot override active urgent speech',async()=>{
  const h=harness({cancelCallback:true})
  h.controller.offer(h.event('chair','observation',{age_ms:0}))
  h.controller.offer(h.event('stop-now','urgent'))
  h.controller.offer(h.event('queued-lower-priority','observation',{age_ms:0}))
  await Promise.resolve()
  assert.equal(h.spoken.at(-1).text,'stop-now')
})

test('urgent event discards previously queued routine output',()=>{
  const h=harness()
  h.controller.offer(h.event('route','route'))
  h.controller.offer(h.event('old-chair','observation',{age_ms:0}))
  h.controller.offer(h.event('stop','urgent'))
  h.spoken.at(-1).onend()
  assert.equal(h.spoken.some(x=>x.text==='old-chair'),false)
})

test('repeated backend event ID speaks once',()=>{
  const h=harness(); const event=h.event('same-event','route')
  assert.equal(h.controller.offer(event),true)
  assert.equal(h.controller.offer(event),false)
  assert.equal(h.spoken.length,1)
})
