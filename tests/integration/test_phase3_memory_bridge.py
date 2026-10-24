"""Phase 3's real DB + worker + YOLO, with a clearly labeled static fixture."""
from pathlib import Path
import time
import pytest
pytest.importorskip('stride_backend.memory',reason='Phase 3 required on PYTHONPATH')
from fastapi.testclient import TestClient
from app.vision.phase2 import build_detector
from stride_backend.main import create_app
from stride_backend.settings import Settings


def wait_for(client,headers,predicate,path='/vision/latest',timeout=3):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        response=client.get(path,headers=headers,params={'session_id':'memory-test'})
        assert response.status_code==200,response.text
        result=response.json()
        if predicate(result): return result
        time.sleep(.02)
    raise AssertionError(result)


@pytest.mark.skipif(not Path('qa/private/bus.jpg').exists() or not Path('models/yolov8n.onnx').exists(),
                    reason='Explicit image fixture and exported model required')
def test_stable_tracks_saved_at_confirmed_place_and_survive_restart(tmp_path):
    settings=Settings(_env_file=None,local_dev=True,session_tokens={'memory-test':'fixture-ui'},
                      database_path=tmp_path/'memory.sqlite3',record_stable_sightings=True)
    app=create_app(settings,detector=build_detector())
    headers={'X-Session-Token':'fixture-ui'}
    with TestClient(app) as client:
        # This is a temporary fixture layout, never human verification of a real route.
        app.state.route_catalog.mark_checked('demo-hallway','TEST FIXTURE ONLY; not a physical route')
        route=client.post('/route',headers=headers,json={'session_id':'memory-test','route_id':'demo-hallway',
                         'action':'start','action_id':'route-start'}).json()
        confirmed=client.post('/route',headers=headers,json={'session_id':'memory-test',
            'navigation_id':route['navigation_id'],'expected_revision':route['state_revision'],
            'action':'confirm','action_id':'confirm-once'})
        assert confirmed.status_code==200,confirmed.text
        assert confirmed.json()['confirmed_checkpoint_count']==1
        assert client.post('/vision',headers=headers,json={'session_id':'memory-test','action':'start','action_id':'vision-start'}).status_code==200
        def upload(seq):
            response=client.post('/frame',headers=headers,data={'session_id':'memory-test','device_id':'fixture-camera',
                'boot_id':'fixture-boot','sequence':seq,'frame_id':str(seq),'captured_ms':10000,
                'source':'fixture','origin':'fixture','source_revision':0},
                files={'file':('fixture.jpg',Path('qa/private/bus.jpg').read_bytes(),'image/jpeg')})
            assert response.status_code==202,response.text
            return wait_for(client,headers,lambda r:r['frame_id']==str(seq) and not r['in_flight'])
        upload(1)
        assert client.get('/memory',headers=headers,params={'session_id':'memory-test'}).json()['sightings']==[]
        upload(2)
        memory=wait_for(client,headers,lambda r:bool(r['sightings']),path='/memory')
        saved=memory['sightings']
        assert {'bus','person'}<={s['label'] for s in saved}
        assert all(s['source']=='fixture' and s['observation']=='last_seen' and s['checkpoint_id']=='demo-hallway:A' for s in saved)
        upload(3)
        # The next identical observation is not another DB event inside cooldown.
        time.sleep(.25)
        later=client.get('/memory',headers=headers,params={'session_id':'memory-test'}).json()
        assert {s['sighting_id'] for s in later['sightings']}=={s['sighting_id'] for s in saved}
        assert {s['frame_id'] for s in later['sightings']}=={'2'}
    restarted=create_app(settings)
    with TestClient(restarted) as client:
        memory=client.get('/memory',headers=headers,params={'session_id':'memory-test'}).json()
        assert memory['navigation']['state']=='paused'
        assert memory['navigation']['confirmed_checkpoint_count']==1
        assert {s['sighting_id'] for s in memory['sightings']}=={s['sighting_id'] for s in saved}
        assert memory['navigation']['physical_position_known'] is False
