"""Actual local webcam/model with injected faults; no HTTP/phone/hardware claim."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import threading
import time
from uuid import uuid4
import cv2
import numpy as np
from app.vision.capture import encode_capture
from app.vision.model import OnnxDetector
from app.vision.service import Frame, VisionService, epoch_ms


class FaultDetector:
    def __init__(self,model):
        self.model=model; self.delay=0; self.gate=None
        self.started=threading.Event(); self.lock=threading.Lock()
        self.inflight=0; self.peak=0
    def arm(self):
        self.started.clear(); self.gate=threading.Event()
    def __call__(self,jpeg):
        with self.lock:
            self.inflight+=1; self.peak=max(self.peak,self.inflight)
        gate=self.gate
        try:
            if gate is not None:
                self.started.set()
                if not gate.wait(12): raise RuntimeError('Fault gate timed out')
            if self.delay: time.sleep(self.delay)
            return self.model(jpeg)
        finally:
            with self.lock: self.inflight-=1


async def run(args):
    model=OnnxDetector(args.model)
    cap=cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
    cases={}; source_stats={'captures':0,'nearly_black':0}
    sessions=[]; detectors=[]; counter=0
    async def capture(sid,revision=1):
        nonlocal counter
        captured=epoch_ms()
        ok,image=await asyncio.to_thread(cap.read)
        if not ok: raise RuntimeError('Actual webcam read failed')
        jpeg,dimensions,quality=encode_capture(image)
        counter+=1; source_stats['captures']+=1
        source_stats['nearly_black']+=quality['nearly_black']
        return Frame(sid,'same-physical-webcam','fault-run-boot',counter,str(uuid4()),captured,
                     revision,'real','browser_camera',jpeg,width=dimensions[0],height=dimensions[1],received_ms=epoch_ms())
    def session(name):
        observations=[]; invalid=[]
        detector=FaultDetector(model); detectors.append(detector)
        async def callback(result):
            if not service.is_current(result): invalid.append(result['frame_id'])
            observations.append(result)
        service=VisionService(detector=detector,on_observation=callback)
        service.bind(name,1,'real','browser_camera'); service.control(name,'start',1)
        sessions.append(service)
        return service,detector,observations,invalid
    async def settle(service,sid):
        worker=service.sessions[sid].worker
        if worker: await asyncio.wait_for(asyncio.shield(worker),4)
        callback=service.sessions[sid].callback_worker
        if callback: await asyncio.wait_for(asyncio.shield(callback),1)
    async def checked(name,body):
        first=len(sessions)
        try: cases[name]=dict(await body(),status='PASS')
        except Exception as exc: cases[name]={'status':'FAIL','error':str(exc)}
        finally:
            for detector in detectors[first:]:
                if detector.gate: detector.gate.set()
            for service in sessions[first:]:
                await service.close()

    try:
        if not cap.isOpened(): raise RuntimeError('Webcam unavailable; no fixture substitution')
        # Exclude driver initialization only; no startup frame is restamped fresh.
        for _ in range(3):
            ok,_=await asyncio.to_thread(cap.read)
            if not ok: raise RuntimeError('Camera warmup failed')

        async def overload():
            sid='overload'; service,detector,observations,invalid=session(sid)
            detector.delay=.2
            began=time.monotonic(); deadline=began; peak_pending=0; offered=0
            while time.monotonic()-began<args.overload_seconds:
                f=await capture(sid)
                service.offer_frame(f); offered+=1
                peak_pending=max(peak_pending,int(service.sessions[sid].pending is not None))
                deadline+=1/30
                await asyncio.sleep(max(0,deadline-time.monotonic()))
            await settle(service,sid)
            final=service.snapshot(sid)
            ages=[o['completed_ms']-o['captured_ms'] for o in observations]
            assert offered>10 and final['dropped_frames']>0,'No actual overload was exercised'
            assert peak_pending==1 and detector.peak==1,'Work queue/model concurrency exceeded bound'
            assert observations and not invalid and max(ages)<1000,'Expired publication'
            assert final['frame_id']==f.frame_id,'Newest offered frame was not eventually processed'
            return {'offered':offered,'published':len(observations),'dropped':final['dropped_frames'],
                    'pending_peak':peak_pending,'model_inflight_peak':detector.peak,
                    'age_p95_ms':float(np.percentile(ages,95)),'age_max_ms':max(ages)}
        await checked('inference_overload',overload)

        async def stale_completion():
            sid='stale-completion'; service,detector,observations,invalid=session(sid)
            detector.delay=1.15
            service.offer_frame(await capture(sid)); await settle(service,sid)
            final=service.snapshot(sid)
            assert not observations and final['objects']==[] and final['status']=='unavailable'
            assert final['dropped_frames']==1 and final['inferred_frames']==1
            return {'injected_delay_ms':1150,'published':len(observations),
                    'dropped':final['dropped_frames'],'final_status':final['status']}
        await checked('expired_inflight_result',stale_completion)

        async def blackout():
            sid='capture-blackout'; service,_,observations,invalid=session(sid)
            service.offer_frame(await capture(sid)); await settle(service,sid)
            before=service.snapshot(sid)
            assert before['status']=='live' and observations
            await asyncio.sleep(1.1)
            after=service.snapshot(sid)
            assert after['status']=='stale' and after['objects']==[] and after['speech_event'] is None
            assert not service.is_current(observations[-1])
            return {'before':before['status'],'after':after['status'],'age_ms':after['age_ms'],
                    'last_objects_count':len(before['objects']),'current_objects_count':len(after['objects'])}
        await checked('capture_loss_and_read_time_expiry',blackout)

        async def transition(action):
            sid='transition-'+action; service,detector,observations,invalid=session(sid)
            service.offer_frame(await capture(sid)); await settle(service,sid)
            old_tracks={o['track_id'] for o in service.snapshot(sid)['objects']}
            observations.clear(); detector.arm()
            retired=await capture(sid); service.offer_frame(retired)
            assert await asyncio.to_thread(detector.started.wait,2)
            try:
                if action=='source-switch':
                    service.bind(sid,2,'real','browser_camera'); revision=2
                else:
                    service.control(sid,action,1); revision=1
                paused=service.snapshot(sid)
                assert paused['status']=='paused' and paused['objects']==[]
                try: service.offer_frame(retired)
                except ValueError: pass
                else: raise AssertionError('Retired/paused frame accepted')
                service.control(sid,'resume',revision)
                fresh=await capture(sid,revision); service.offer_frame(fresh)
            finally: detector.gate.set()
            await settle(service,sid)
            final=service.snapshot(sid)
            assert not invalid and observations and all(o['frame_id']!=retired.frame_id for o in observations)
            assert final['frame_id']==fresh.frame_id and final['source_revision']==revision
            assert old_tracks.isdisjoint({o['track_id'] for o in final['objects']})
            return {'final_revision':revision,'retired_frame_published':False,'fresh_frame_published':True,
                    'old_tracks_count':len(old_tracks),'new_tracks_count':len(final['objects']),
                    'switch_scope':'logical producer/revision on same physical webcam'}
        for action in ['source-switch','pause','stop']:
            async def body(action=action): return await transition(action)
            await checked(action,body)

        async def switch_storm():
            sid='switch-storm'; service,detector,observations,invalid=session(sid)
            detector.arm(); service.offer_frame(await capture(sid))
            assert await asyncio.to_thread(detector.started.wait,2)
            peak=0
            try:
                for revision in range(2,32):
                    service.bind(sid,revision,'real','browser_camera'); service.control(sid,'start',revision)
                    newest=await capture(sid,revision); service.offer_frame(newest)
                    peak=max(peak,sum(not t.done() for t in service.workers))
            finally: detector.gate.set()
            await settle(service,sid)
            final=service.snapshot(sid)
            assert peak==1 and detector.peak==1,'Retired workers accumulated'
            assert final['frame_id']==newest.frame_id and final['source_revision']==31
            assert not invalid and all(o['source_revision']==31 for o in observations)
            return {'source_changes':30,'waiting_or_running_workers_peak':peak,
                    'model_inflight_peak':detector.peak,'only_final_revision_published':True}
        await checked('rapid_source_replacement',switch_storm)
    finally:
        cap.release()
        for detector in detectors:
            if detector.gate: detector.gate.set()
        for service in sessions: await service.close()
    report={'source':'real','origin':'browser_camera','capture_adapter':'opencv_webcam','model_sha256':hashlib.sha256(Path(args.model).read_bytes()).hexdigest(),
            'input':source_stats,'cases':cases,'status':'PASS' if cases and all(c['status']=='PASS' for c in cases.values()) else 'FAIL',
            'scope':'Actual local capture and YOLO with injected delays/logical source changes. No hosted network, physical camera switch or phone speech claim.'}
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',default='models/yolov8n.onnx'); p.add_argument('--camera',type=int,default=0)
    p.add_argument('--overload-seconds',type=float,default=6)
    p.add_argument('--output',default='qa/webcam-fault-results.json')
    args=p.parse_args()
    if args.overload_seconds<2: p.error('Use at least two seconds of overload')
    result=asyncio.run(run(args))
    raise SystemExit(0 if result['status']=='PASS' else 1)
