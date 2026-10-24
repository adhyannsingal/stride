"""Contract harness only: the fixture backend below is not a production app."""
import asyncio
import io
from uuid import uuid4
from PIL import Image
from fastapi import FastAPI, Request, HTTPException
from fastapi.testclient import TestClient
from app.vision.model import Detection, read_jpeg
from app.vision.router import router
from app.vision.service import Frame, VisionService


def test_canonical_mount_ingest_callback_and_action_dedup():
    sid,device,boot=str(uuid4()),'fixture-camera','fixture-boot'
    clock=[10000]; candidates=[]; actions={}
    async def observation(result):
        if vision.is_current(result): candidates.append(result)
    vision=VisionService(detector=lambda _:[Detection('chair',.9,(.1,.2,.3,.8))],clock=lambda:clock[0],on_observation=observation)
    vision.bind(sid,1,'fixture','fixture')
    app=FastAPI(); app.state.vision=vision; app.include_router(router)
    class FixtureCanonicalBackend:
        def auth(self,request):
            if request.headers.get('x-fixture-auth')!='yes': raise HTTPException(401)
        async def control(self,request,service):
            self.auth(request)
            body=await request.json()
            if body['session_id']!=sid: raise HTTPException(403)
            if body['action_id'] not in actions:
                actions[body['action_id']]=service.control(sid,body['action'],1)
            return dict(service.snapshot(sid),state_seq=1)
        async def latest(self,request,service):
            self.auth(request)
            if request.query_params.get('session_id')!=sid: raise HTTPException(403)
            return dict(service.snapshot(sid),state_seq=1)
    app.state.vision_api=FixtureCanonicalBackend()
    @app.post('/frame')
    async def canonical_fixture_ingest(request: Request):
        app.state.vision_api.auth(request)
        jpeg=await request.body(); image=read_jpeg(jpeg)
        seq=int(request.headers['x-sequence'])
        vision.offer_frame(Frame(sid,device,boot,seq,str(seq),clock[0],1,'fixture','fixture',jpeg,width=image.width,height=image.height,received_ms=clock[0]))
        await vision.sessions[sid].worker
        await vision.sessions[sid].callback_worker
        return {'frame_id':str(seq)}
    jpeg=io.BytesIO(); Image.new('RGB',(640,480)).save(jpeg,format='JPEG')
    with TestClient(app) as client:
        headers={'x-fixture-auth':'yes'}
        action={'session_id':sid,'action_id':str(uuid4()),'action':'start'}
        assert client.post('/vision',json=action,headers=headers).status_code==200
        for seq in [1,2]:
            assert client.post('/frame',content=jpeg.getvalue(),headers=dict(headers,**{'x-sequence':str(seq)})).status_code==200
            clock[0]+=100
        assert candidates[-1]['candidate_event'] is not None
        # Retrying start must not reset live results/tracks.
        assert client.post('/vision',json=action,headers=headers).json()['frame_id']=='2'
        latest=client.get('/vision/latest',params={'session_id':sid},headers=headers).json()
        assert latest['objects'][0]['box']==[.1,.2,.3,.8]
        assert latest['speech_event'] is None  # final arbiter is deliberately absent
        pause=dict(action,action_id=str(uuid4()),action='pause')
        assert client.post('/vision',json=pause,headers=headers).json()['objects']==[]
        assert not vision.is_current(candidates[-1])
