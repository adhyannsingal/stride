import { test } from 'node:test'
import assert from 'node:assert/strict'
import { SpeechController, PollController, BrowserCameraController } from '../src/app/controllers.ts'
import { freshVision, newerVision, obstacleState, visionActionAllowed, routeSpeech, visionSpeech, PendingAction } from '../src/app/policy.ts'
import type { SpokenEvent, CameraOptions } from '../src/app/controllers.ts'
import type { VisionLatest, NavigationProgress, DeviceStatus } from '../src/app/api.ts'

const tick = () => new Promise(r => setTimeout(r, 5))
function speechHarness(t: any) {
  let now = 0
  const spoken: any[] = []
  let cancels = 0
  const synth = {speak: (u: any) => spoken.push(u), cancel: () => { cancels++; spoken.at(-1)?.onend?.() }}
  Object.defineProperty(globalThis,'window',{value:{speechSynthesis:synth},configurable:true})
  const controller = new SpeechController(() => now, () => synth as any, text => ({text}) as any)
  controller.enable(); t.after(() => controller.cancel())
  const event = (id: string, kind: SpokenEvent['kind'] = 'observation', expiresAt = 1000, valid = () => true) => ({id,text:id,kind,expiresAt,valid})
  return {controller,event,spoken,now:(value:number) => now=value,cancels:() => cancels}
}
test('speech needs explicit enable', t => { const h=speechHarness(t); const c=new SpeechController(); c.enqueue(h.event('x')); assert.equal(h.spoken.length,0) })
test('dedupe survives cancel', t => { const h=speechHarness(t); h.controller.enqueue(h.event('a')); h.controller.cancel();h.controller.enqueue(h.event('a'));assert.equal(h.spoken.length,1) })
test('expired event never plays', t => {const h=speechHarness(t);h.now(1001);h.controller.enqueue(h.event('a'));assert.equal(h.spoken.length,0)})
test('queued event expires before playback', t => {const h=speechHarness(t);h.controller.enqueue(h.event('a','route',5000));h.controller.enqueue(h.event('b'));h.now(1100);h.spoken[0].onend();assert.equal(h.spoken.length,1)})
test('urgent cancels observation and discards lower queue', t => {const h=speechHarness(t);h.controller.enqueue(h.event('a'));h.controller.enqueue(h.event('b'));h.controller.enqueue(h.event('stop','urgent'));assert.equal(h.cancels(),1);assert.deepEqual(h.spoken.map(u=>u.text),['a','stop']);h.spoken[1].onend();assert.equal(h.spoken.length,2)})
test('fault interrupts route', t => {const h=speechHarness(t);h.controller.enqueue(h.event('turn','route'));h.controller.enqueue(h.event('fault','fault'));assert.equal(h.spoken.at(-1).text,'fault')})
test('priority ordered queue', t => {const h=speechHarness(t);h.controller.enqueue(h.event('stop','urgent'));h.controller.enqueue(h.event('info','info'));h.controller.enqueue(h.event('route','route'));h.spoken[0].onend();assert.equal(h.spoken[1].text,'route')})
for (const reason of ['route revision','session','source revision','pause','block']) test(`${reason} invalidates current and queued speech`,t=>{const h=speechHarness(t);let valid=true;h.controller.enqueue(h.event('a','route',5000,()=>valid));h.controller.enqueue(h.event('b','route',5000,()=>valid));valid=false;h.controller.reconcile();assert.equal(h.controller.pending(),0);assert.equal(h.cancels(),1);h.spoken[0].onend();assert.equal(h.spoken.length,1)})
test('queue remains bounded',t=>{const h=speechHarness(t);h.controller.enqueue(h.event('stop','urgent'));for(let i=0;i<100;i++)h.controller.enqueue(h.event('e'+i));assert.equal(h.controller.pending(),8)})
test('disable observation reconciles current speech',t=>{const h=speechHarness(t);h.controller.enqueue(h.event('a'));h.controller.observations=false;h.controller.reconcile();assert.equal(h.cancels(),1)})
test('reset permits IDs only in explicit new session',t=>{const h=speechHarness(t);h.controller.enqueue(h.event('a'));h.controller.reset();h.controller.enqueue(h.event('a'));assert.equal(h.spoken.length,2)})
const vision = (v: Partial<VisionLatest> = {}): VisionLatest => ({state:'active',status:'live',generation:1,state_seq:2,source_revision:1,age_ms:100,objects:[],detector_configured:true,source:'real',origin:'browser_camera',device_id:'a',frame_id:'f',speech_event:null,last_inference_error:null,...v})
test('freshness expires without another HTTP response',()=>{assert.ok(freshVision(vision(),0,500));assert.ok(!freshVision(vision(),0,901))})
for (const v of [vision({state:'paused'}),vision({status:'stale'}),vision({age_ms:null}),vision({age_ms:1001})]) test(`no current boxes for ${v.state}/${v.status}/${v.age_ms}`,()=>assert.ok(!freshVision(v,0,0)))
for(const v of [vision({generation:0}),vision({state_seq:1}),vision({source_revision:0})])test('ignore older vision identity '+JSON.stringify(v).slice(0,100),()=>assert.ok(!newerVision(vision(),v)))
test('terminal stopped session has no start or resume',()=>{assert.ok(!visionActionAllowed('stopped','start'));assert.ok(!visionActionAllowed('stopped','resume'));assert.ok(visionActionAllowed('paused','resume'))})
test('no fabricated observation without event',()=>assert.equal(visionSpeech('s',vision(),0,()=>true),null))
test('unaligned capture cannot speak',()=>assert.equal(visionSpeech('s',vision({speech_event:{event_id:'e',text:'chair',generation:1,source_revision:1}}),performance.now(),()=>true),null))
test('aligned fresh authorized event normalizes',()=>assert.equal(visionSpeech('s',vision({camera_clock_aligned:true,freshness_basis:'aligned_capture',speech_event:{event_id:'e',text:'chair',generation:1,source_revision:1}}),performance.now(),()=>true)?.text,'chair'))
test('invalid route event cannot speak',()=>assert.equal(routeSpeech('s',{state:'paused',guidance_event:{valid:true}} as NavigationProgress,1000,()=>true),null))
test('device danger outranks navigation clear',()=>assert.equal(obstacleState({obstacle_state:'clear'} as NavigationProgress,{measurement_fresh:true,sensor_valid:true,obstacle_state:'danger'} as DeviceStatus,true,true),'danger'))
test('stale clear becomes unknown',()=>assert.equal(obstacleState(null,{obstacle_state:'clear'} as DeviceStatus,false,true),'unknown'))
test('unknown is not clear, absent association is null',()=>{assert.equal(obstacleState(null,null,false,true),'unknown');assert.equal(obstacleState(null,null,false,false),null)})
test('uncertain action preserves ID and exact original payload',()=>{const a=new PendingAction<{revision:number}>();const first=a.begin({revision:1});assert.equal(a.begin({revision:2}),first);assert.equal(a.value?.payload.revision,1);a.clear();assert.notEqual(a.begin({revision:2}).id,first.id)})
test('poll never overlaps, aborts and drops late results',async()=>{const p=new PollController();let calls=0,accepted=0;let release!:()=>void;let signal!:AbortSignal;p.start(async s=>{calls++;signal=s;await new Promise<void>(r=>release=r);return 1},()=>accepted++,()=>{},1);await tick();await tick();assert.equal(calls,1);p.stop();assert.ok(signal.aborted);release();await tick();assert.equal(accepted,0)})
test('poll failure backs off without fixture fallback',async()=>{const p=new PollController();let failures=0,accepted=0;p.start(async()=>{throw Error('offline')},()=>accepted++,()=>failures++,200);await tick();p.stop();assert.equal(failures,1);assert.equal(accepted,0)})
function cameraHarness() {
 let opens=0,stops=0,allowed=true
 const video={srcObject:null,play:async()=>{},readyState:2,videoWidth:1280,videoHeight:720} as any
 Object.defineProperty(globalThis,'navigator',{value:{mediaDevices:{getUserMedia:async()=>{opens++;return {getTracks:()=>[{stop:()=>stops++}]}}}},configurable:true})
 Object.defineProperty(globalThis,'document',{value:{createElement:()=>({getContext:()=>({drawImage:()=>{}}),toBlob:(resolve:any)=>resolve(new Blob(['jpeg'],{type:'image/jpeg'}))})},configurable:true})
 const opts:CameraOptions={sessionId:'s',role:'browser',consent:true,userGesture:true,sourceRevision:7,singleProducer:true,allowed:()=>allowed}
 return {opts,video,opens:()=>opens,stops:()=>stops,revoke:()=>allowed=false}
}
for(const patch of [{userGesture:false},{consent:false},{role:'viewer'},{role:'glasses'},{singleProducer:false}])test('capture gate '+JSON.stringify(patch),async()=>{const h=cameraHarness();const c=new BrowserCameraController();await assert.rejects(c.start(h.video,{...h.opts,...patch} as CameraOptions,()=>{}));assert.equal(h.opens(),0)})
test('one upload in flight, real metadata, cancellation releases tracks',async()=>{const h=cameraHarness();let calls=0;let release!:(x:any)=>void;let signal!:AbortSignal;let form!:FormData;const c=new BrowserCameraController(async(f,s)=>{calls++;form=f;signal=s!;return new Promise(r=>release=r)});const run=c.start(h.video,h.opts,()=>{});await tick();await tick();assert.equal(calls,1);assert.equal(form.get('source_revision'),'7');assert.equal(form.get('source'),'real');assert.equal(form.get('sequence'),'1');h.revoke();c.stop();release({received_ms:0,replaced_pending:false});await run;assert.ok(signal.aborted);assert.equal(h.stops(),1);assert.equal(h.video.srcObject,null);assert.equal(calls,1)})
test('late permission after stop releases tracks without upload',async()=>{const h=cameraHarness();let resolve!:(v:any)=>void;Object.defineProperty(globalThis,'navigator',{value:{mediaDevices:{getUserMedia:()=>new Promise(r=>resolve=r)}},configurable:true});let stops=0,uploads=0;const c=new BrowserCameraController(async()=>{uploads++;return {} as any});const pending=c.start(h.video,h.opts,()=>{});await tick();c.stop();resolve({getTracks:()=>[{stop:()=>stops++}]});await pending;assert.equal(stops,1);assert.equal(uploads,0)})
test('permission denial gives actionable error',async()=>{const h=cameraHarness();(navigator.mediaDevices as any).getUserMedia=async()=>{throw new DOMException('denied','NotAllowedError')};await assert.rejects(new BrowserCameraController().start(h.video,h.opts,()=>{}),/permission denied/)})
test('upload failure is visible and stops capture',async()=>{const h=cameraHarness();let error='';const c=new BrowserCameraController(async()=>{throw Error('offline')});await assert.rejects(c.start(h.video,h.opts,e=>error=e),/offline/);assert.equal(error,'offline');assert.equal(h.stops(),1)})
