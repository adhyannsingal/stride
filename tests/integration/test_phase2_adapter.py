"""Run with PYTHONPATH=.:backend_phase2; Phase 2 remains the only API/controller."""
import asyncio
from dataclasses import replace
from pathlib import Path
import time
from uuid import uuid4
import pytest

pytest.importorskip('stride_backend',reason='Add backend_phase2 to PYTHONPATH for combined integration')
from fastapi.testclient import TestClient
from app.vision.model import Detection as ModelDetection
from app.vision.phase2 import Phase2Detector, build_detector
from stride_backend.main import create_app
from stride_backend.models import ReceivedFrameMetadata
from stride_backend.settings import Settings
from stride_backend.store import Frame, monotonic_ms


def frame(generation=1,revision=0,sequence=1):
    meta=ReceivedFrameMetadata(session_id='integration',device_id='camera',boot_id='boot',
        frame_id=str(sequence),sequence=sequence,captured_ms=10000,source='fixture',origin='fixture',
        source_revision=revision,receipt_id=str(uuid4()),received_ms=10000,size_bytes=5,width=64,height=48)
    return Frame(b'fixture',meta,monotonic_ms(),generation=generation)


def test_adapter_preserves_receipt_tracks_and_generation_without_final_speech():
    model=lambda _: [ModelDetection('chair',.9,(.1,.2,.4,.8))]
    detector=Phase2Detector(model)
    a=frame(); b=frame(sequence=2)
    first=asyncio.run(detector.detect(a)); second=asyncio.run(detector.detect(b))
    assert first.frame==a.metadata and second.frame==b.metadata
    assert first.objects[0].bbox==(.1,.2,.4,.8)
    assert first.objects[0].track_id==second.objects[0].track_id
    assert first.speech_event is None and second.speech_event is None
    resumed=asyncio.run(detector.detect(frame(generation=2,sequence=3)))
    switched=asyncio.run(detector.detect(frame(generation=3,revision=1,sequence=4)))
    assert resumed.objects[0].track_id!=first.objects[0].track_id
    assert switched.objects[0].track_id!=resumed.objects[0].track_id


def test_adapter_session_state_is_bounded():
    detector=Phase2Detector(lambda _: [],max_sessions=1)
    a=frame(); asyncio.run(detector.detect(a))
    b=replace(a,metadata=a.metadata.model_copy(update={'session_id':'other'}))
    with pytest.raises(RuntimeError): asyncio.run(detector.detect(b))


@pytest.mark.skipif(not Path('qa/private/bus.jpg').exists() or not Path('models/yolov8n.onnx').exists(),
                    reason='Explicit local fixture and exported model required; no download/fallback')
def test_actual_yolo_through_phase2_auth_ingest_worker_and_latest():
    detector=build_detector()
    settings=Settings(_env_file=None,local_dev=True,device_token='fixture-device-token',
                      session_tokens={'integration':'fixture-ui-token'})
    app=create_app(settings,detector=detector)
    headers={'X-Session-Token':'fixture-ui-token'}
    with TestClient(app) as client:
        assert client.get('/vision/latest',params={'session_id':'integration'}).status_code==401
        action={'session_id':'integration','action_id':'start-once','action':'start'}
        assert client.post('/vision',headers=headers,json=action).status_code==200
        receipt=client.post('/frame',headers=headers,data={
            'session_id':'integration','device_id':'fixture-camera','boot_id':'fixture-boot',
            'frame_id':'official-bus-fixture','sequence':1,'captured_ms':10000,
            'source':'fixture','origin':'fixture','source_revision':0},
            files={'file':('fixture.jpg',Path('qa/private/bus.jpg').read_bytes(),'image/jpeg')})
        assert receipt.status_code==202, receipt.text
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            result=client.get('/vision/latest',headers=headers,params={'session_id':'integration'}).json()
            if result['status']=='live': break
            time.sleep(.01)
        assert result['status']=='live',result
        assert result['source']=='fixture' and result['frame_id']=='official-bus-fixture'
        assert {'bus','person'} <= {obj['label'] for obj in result['objects']}
        assert result['speech_event'] is None
        assert result['freshness_basis']=='server_receipt' and not result['camera_clock_aligned']
        assert client.post('/vision',headers=headers,json=action).json()['duplicate']
        pause=dict(action,action_id='pause-once',action='pause')
        assert client.post('/vision',headers=headers,json=pause).status_code==200
        state=client.get('/vision/latest',headers=headers,params={'session_id':'integration'}).json()
        assert state['status']=='paused' and state['objects']==[]
