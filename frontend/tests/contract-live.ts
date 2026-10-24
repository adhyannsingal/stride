// Opt-in actual HTTP check. Requires backend_fixture.py and Vite, no physical hardware.
import assert from 'node:assert/strict'
import {strideApi, ApiError} from '../src/app/api.ts'
const networkFetch=globalThis.fetch
let cookie=''
globalThis.fetch=async(path,init={})=>{
 const response=await networkFetch(`http://127.0.0.1:8443${path}`,{...init,headers:{...init.headers,Cookie:cookie}})
 const issued=response.headers.get('set-cookie');if(issued)cookie=issued.split(';')[0]
 return response
}
let checks=0
const ok=(name:string)=>{checks++;console.log('PASS',name)}
assert.equal((await strideApi.health()).status,'ok');ok('GET /health')
assert.ok((await strideApi.time()).server_ms>0);ok('GET /time')
await strideApi.connect('test-session','test-only-token');assert.match(cookie,/stride_session=/);ok('POST /auth/session sets cookie')
const routes=await strideApi.routes('test-session');assert.ok(routes.routes.some(r=>r.checked));ok('GET /routes')
let n=await strideApi.routeAction('test-session',crypto.randomUUID(),'start','demo-hallway');assert.equal(n.state,'guiding');ok('POST /route start')
const id=crypto.randomUUID();const first=await strideApi.routeAction('test-session',id,'confirm',undefined,n);const duplicate=await strideApi.routeAction('test-session',id,'confirm',undefined,n);assert.equal(duplicate.confirmed_checkpoint_count,1);assert.ok(duplicate.duplicate);ok('confirm retry idempotency')
await assert.rejects(strideApi.routeAction('test-session',crypto.randomUUID(),'confirm',undefined,n),e=>e instanceof ApiError && e.status===409);ok('stale revision conflict')
n=first;const mem=await strideApi.memory('test-session');assert.equal(mem.navigation?.confirmed_checkpoint_count,1);assert.deepEqual(mem.sightings,[]);ok('GET /memory')
await strideApi.visionAction('test-session',crypto.randomUUID(),'start');let v=await strideApi.visionLatest('test-session');assert.equal(v.state,'active');assert.equal(v.detector_configured,false);ok('POST /vision and GET /vision/latest, detector honestly unavailable')
// Real JPEG bytes generated from a 1x1 image fixture (not a physical camera).
const jpeg=await import('node:fs/promises').then(fs=>fs.readFile(process.env.TEST_JPEG!))
const form=new FormData();form.append('file',new Blob([jpeg],{type:'image/jpeg'}),'test.jpg')
for(const [k,val] of Object.entries({session_id:'test-session',device_id:'test-camera',boot_id:'boot',frame_id:'test-frame',sequence:1,captured_ms:Date.now(),source:'fixture',origin:'fixture',source_revision:v.source_revision}))form.append(k,String(val))
assert.ok((await strideApi.uploadFrame(form)).received_ms);ok('POST /frame accepts multipart JPEG')
await strideApi.pairDevice('test-controller','test-session');const d=await strideApi.deviceStatus('test-controller','test-session');assert.equal(d.obstacle_state,'unknown');assert.equal(d.current_distance_cm,null);ok('POST /device/pair and GET /device/status')
const blocked=(await strideApi.memory('test-session')).navigation!;assert.equal(blocked.state,'blocked');await strideApi.routeAction('test-session',crypto.randomUUID(),'stop',undefined,blocked);ok('unknown sensor blocks; Stop accepted')
await strideApi.visionAction('test-session',crypto.randomUUID(),'stop',v.generation);v=await strideApi.visionLatest('test-session');assert.equal(v.state,'stopped');await assert.rejects(strideApi.visionAction('test-session',crypto.randomUUID(),'start',v.generation),e=>e instanceof ApiError&&e.status===409);ok('terminal vision session enforced')
console.log(`${checks} actual HTTP checks passed; synthetic fixture inputs; no detector/hardware.`)
