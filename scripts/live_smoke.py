"""Actual webcam -> existing API diagnostic. Select canonical or Phase 2 protocol.
Credentials are private environment inputs; no alternate backend/UI is created.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import time
from uuid import uuid4
import cv2
import httpx
import numpy as np
from app.vision.capture import encode_capture


async def run(a, *, credentials=None, trusted_local_alignment=None):
    headers=dict(credentials or {})
    if not headers:
        if os.environ.get('STRIDE_UI_COOKIE'): headers['Cookie']=os.environ['STRIDE_UI_COOKIE']
        elif a.protocol=='phase2' and os.environ.get('STRIDE_SESSION_TOKEN'):
            headers['X-Session-Token']=os.environ['STRIDE_SESSION_TOKEN']
        else: raise RuntimeError('Set STRIDE_UI_COOKIE or Phase 2 STRIDE_SESSION_TOKEN privately')
    if not a.base_url.startswith(('https://','http://127.0.0.1:','http://localhost:')):
        raise RuntimeError('Use HTTPS or loopback development origin')
    phase2=a.protocol=='phase2'
    boot=str(uuid4()); cap=None; started=False; owned=True
    ages,completion_ages=[],[]
    results=uploads=errors=dark=capture_rejections=0
    last=None; result=None; observed={}; failure=None
    async with httpx.AsyncClient(base_url=a.base_url,headers=headers,timeout=3) as client:
        async def action(name):
            reply=await client.post('/vision',json={'session_id':a.session_id,'action_id':str(uuid4()),'action':name})
            reply.raise_for_status(); return reply.json()
        before=time.time_ns()//1_000_000
        response=await client.get('/time'); response.raise_for_status()
        after=time.time_ns()//1_000_000
        if after-before>500: raise RuntimeError('Clock-sync RTT exceeds 500 ms')
        offset=response.json()['server_ms' if phase2 else 'server_time_ms']-(before+after)//2
        # Never auto-select a source or take over an active producer.
        if phase2:
            current=await client.get('/vision/latest',params={'session_id':a.session_id})
            current.raise_for_status()
            if current.json()['state']!='idle':
                raise RuntimeError('Phase 2 diagnostic requires a new idle provisioned session')
        else:
            current=await client.get('/status',params={'session_id':a.session_id})
            current.raise_for_status()
            camera=current.json().get('camera',{})
            if camera.get('device_id')!=a.device_id:
                raise RuntimeError('Diagnostic device is not the selected camera producer')
        state=await action('start'); started=True
        start=time.monotonic(); last_alignment=0
        try:
            if trusted_local_alignment:
                trusted_local_alignment(boot)
                last_alignment=time.monotonic()
            cap=cv2.VideoCapture(a.camera)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
            if not cap.isOpened(): raise RuntimeError('Camera unavailable')
            while time.monotonic()-start<a.seconds:
                if trusted_local_alignment and time.monotonic()-last_alignment>20:
                    trusted_local_alignment(boot); last_alignment=time.monotonic()
                captured=time.time_ns()//1_000_000+offset
                ok,image=await asyncio.to_thread(cap.read)
                if not ok: raise RuntimeError('Camera read failed')
                jpeg,_,quality=encode_capture(image); dark+=quality['nearly_black']
                if time.time_ns()//1_000_000+offset-captured>=1000:
                    capture_rejections+=1; continue
                uploads+=1
                meta={'session_id':a.session_id,'device_id':a.device_id,'boot_id':boot,
                      'frame_id':str(uuid4()),'sequence':uploads,'captured_ms':captured,
                      'source_revision':state['source_revision']}
                try:
                    if phase2:
                        reply=await client.post('/frame',data=dict(meta,source='real',origin='browser_camera'),
                                                files={'file':('frame.jpg',jpeg,'image/jpeg')})
                    else:
                        upload_headers={'Content-Type':'image/jpeg','X-Clock-Synced':'true',
                            **{'X-'+key.replace('_','-').title():str(value) for key,value in meta.items()}}
                        reply=await client.post('/frame',content=jpeg,headers=upload_headers)
                    reply.raise_for_status()
                    reply=await client.get('/vision/latest',params={'session_id':a.session_id})
                    reply.raise_for_status(); result=reply.json()
                    if result['source_revision']!=state['source_revision'] or result.get('device_id') not in {None,a.device_id}:
                        owned=False; raise RuntimeError('Source replaced; diagnostic stopped without stopping new producer')
                    if result['status']=='live' and result['frame_id']!=last:
                        last=result['frame_id']; results+=1; ages.append(result['age_ms'])
                        completion_ages.append(result['completed_ms']-result['captured_ms'])
                        for obj in result['objects']: observed[obj['label']]=observed.get(obj['label'],0)+1
                except httpx.HTTPError:
                    errors+=1
                await asyncio.sleep(.05)
        except Exception as exc:
            failure=type(exc).__name__+': '+str(exc)
        finally:
            if cap is not None: cap.release()
            if started and owned:
                try: await action('stop')
                except httpx.HTTPError: failure=failure or 'Failed to confirm session stop'
    elapsed=time.monotonic()-start
    def stats(values):
        return {k:float(np.percentile(values,p)) if values else None for k,p in [('p50',50),('p95',95),('max',100)]}
    report={'scope':'actual API camera round trip; hosted phone/AirPods/W11 untested',
            'protocol':a.protocol,'source':'real','origin':'browser_camera','capture_adapter':'opencv_webcam',
            'duration_s':elapsed,'upload_hz':uploads/elapsed,'returned_result_hz':results/elapsed,
            'unique_results':results,'http_errors':errors,'capture_rejections':capture_rejections,
            'nearly_black_frames':dark,'observed_labels':observed,'error':failure,
            'response_age_ms':stats(ages),'capture_to_completion_ms':stats(completion_ages),
            'freshness_basis':result.get('freshness_basis') if result else None,
            'camera_clock_aligned':result.get('camera_clock_aligned') if result else None,
            'clock_alignment_scope':'trusted shared OS clock (local test only)' if trusted_local_alignment else 'server response contract; remote capture alignment not established by client RTT',
            'performance_gate':'PASS' if not failure and not errors and results/elapsed>=5 and completion_ages and np.percentile(completion_ages,95)<=500 else 'FAIL'}
    print(json.dumps(report,indent=2))
    if a.output: Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',required=True); p.add_argument('--session-id',required=True)
    p.add_argument('--device-id',required=True); p.add_argument('--camera',type=int,default=0)
    p.add_argument('--protocol',choices=['canonical','phase2'],default='canonical')
    p.add_argument('--seconds',type=float,default=60); p.add_argument('--output')
    args=p.parse_args()
    if args.seconds<=0: p.error('seconds must be positive')
    asyncio.run(run(args))
