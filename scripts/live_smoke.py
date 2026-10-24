"""Exercise an existing canonical backend; tokens/cookies come from environment.
No alternate auth, session creator, app entrypoint or production /frame handler.
"""
import argparse
import asyncio
import json
import os
import time
from uuid import uuid4
from pathlib import Path
import cv2
import httpx
import numpy as np
from app.vision.capture import encode_capture


async def run(a):
    credentials = {}
    if os.environ.get('STRIDE_UI_COOKIE'):
        credentials['Cookie'] = os.environ['STRIDE_UI_COOKIE']
    else:
        raise RuntimeError('Set STRIDE_UI_COOKIE privately from an authenticated session; never pass it on CLI')
    if not a.base_url.startswith('https://') and not a.base_url.startswith('http://127.0.0.1:'):
        raise RuntimeError('Use HTTPS, or loopback for development')
    ages, results, uploads, errors, last = [], 0, 0, 0, None
    boot = str(uuid4())
    cap = cv2.VideoCapture(a.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
    if not cap.isOpened():
        raise RuntimeError('Camera unavailable')
    async with httpx.AsyncClient(base_url=a.base_url,headers=credentials,timeout=3) as client:
        before = time.time_ns()//1_000_000
        response = await client.get('/time')
        response.raise_for_status()
        after = time.time_ns()//1_000_000
        if after-before>500:
            raise RuntimeError('Clock sync RTT exceeds 500 ms; retry on a healthier connection')
        offset = response.json()['server_time_ms']-(before+after)//2
        async def action(name):
            reply = await client.post('/vision',json={'session_id':a.session_id,'action_id':str(uuid4()),'action':name})
            reply.raise_for_status()
            return reply.json()
        state = await action('start')
        start = time.monotonic()
        try:
            while time.monotonic()-start<a.seconds:
                capture_ms = time.time_ns()//1_000_000+offset
                ok, image = await asyncio.to_thread(cap.read)
                if not ok:
                    raise RuntimeError('Camera read failed')
                jpeg, _, _ = encode_capture(image)
                uploads += 1
                headers = {'Content-Type':'image/jpeg','X-Session-Id':a.session_id,
                           'X-Device-Id':a.device_id,'X-Boot-Id':boot,'X-Frame-Id':str(uuid4()),
                           'X-Sequence':str(uploads),'X-Captured-Ms':str(capture_ms),'X-Clock-Synced':'true','X-Source-Revision':str(state['source_revision'])}
                try:
                    reply = await client.post('/frame',content=jpeg,headers=headers)
                    reply.raise_for_status()
                    reply = await client.get('/vision/latest',params={'session_id':a.session_id})
                    reply.raise_for_status()
                    result = reply.json()
                    if result['source_revision'] != state['source_revision']:
                        raise RuntimeError('Source changed during test')
                    if result['status']=='live' and result['frame_id'] != last:
                        last = result['frame_id']
                        results += 1
                        ages.append(result['age_ms'])
                except httpx.HTTPError:
                    errors += 1
                await asyncio.sleep(.05)
        finally:
            cap.release()
            await action('stop')
    elapsed = time.monotonic()-start
    report = {'scope':'actual API camera round trip; phone/AirPods/W11 untested',
              'source':'real','origin':'browser_camera','base_url':a.base_url,
              'duration_s':elapsed,'upload_hz':uploads/elapsed,'returned_result_hz':results/elapsed,
              'http_errors':errors,'age_ms':{k:float(np.percentile(ages,p)) if ages else None
                  for k,p in [('p50',50),('p95',95),('max',100)]}}
    print(json.dumps(report,indent=2))
    if a.output:
        Path(a.output).write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',required=True)
    p.add_argument('--session-id',required=True)
    p.add_argument('--device-id',required=True)
    p.add_argument('--camera',type=int,default=0)
    p.add_argument('--seconds',type=float,default=60)
    p.add_argument('--output')
    asyncio.run(run(p.parse_args()))
