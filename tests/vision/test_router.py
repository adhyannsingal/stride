from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from app.vision.router import router
from app.vision.service import VisionService


def test_unconfigured_bridge_fails_closed_and_backend_controls_auth():
    app=FastAPI(); app.include_router(router)
    session=str(uuid4())
    service=VisionService(detector=lambda _: [])
    service.bind(session,1,'fixture','fixture'); app.state.vision=service
    with TestClient(app) as client:
        assert client.get('/vision/latest').status_code==503
        class BackendBridge:
            async def latest(self,request,vision):
                if request.headers.get('authorization')!='fixture-auth': raise HTTPException(401)
                if request.query_params.get('session_id')!=session: raise HTTPException(403)
                return dict(vision.snapshot(session),state_seq=123,speech_event=None)
            async def control(self,request,vision):
                raise HTTPException(401)
        app.state.vision_api=BackendBridge()
        assert client.get('/vision/latest').status_code==401
        assert client.post('/vision',json={}).status_code==401
        assert client.get('/vision/latest',params={'session_id':str(uuid4())},headers={'authorization':'fixture-auth'}).status_code==403
        reply=client.get('/vision/latest',params={'session_id':session},headers={'authorization':'fixture-auth'})
        assert reply.status_code==200 and reply.json()['state_seq']==123
