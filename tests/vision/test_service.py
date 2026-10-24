import asyncio
from dataclasses import replace
from types import SimpleNamespace
import threading
import pytest
from app.vision.model import Detection
from app.vision.service import Frame, VisionService


def frame(now=10000, sequence=1, revision=1):
    return Frame('session','camera','boot',sequence,str(sequence),now,revision,'fixture','fixture',b'fixture')


def setup(detector=lambda _: [Detection('chair',.9,(.1,.1,.4,.5))], callback=None):
    now=[10000]
    service=VisionService(detector=detector,clock=lambda:now[0],on_observation=callback)
    service.bind('session',1,'fixture','fixture')
    service.control('session','start',1)
    return service,now


def test_candidate_callback_never_becomes_direct_speech():
    async def run():
        observations=[]
        async def callback(result): observations.append(result)
        s,now=setup(callback=callback)
        for seq in [1,2]:
            s.offer_frame(frame(now[0],seq))
            await s.sessions['session'].worker
            await s.sessions['session'].callback_worker
            now[0]+=100
        snap=s.snapshot('session')
        assert snap['status']=='live' and snap['speech_event'] is None
        assert observations[0]['candidate_event'] is None
        assert observations[1]['candidate_event']['text'].startswith('chair')
        assert s.is_current(observations[1])
        now[0]+=1000
        assert not s.is_current(observations[1])
        assert s.snapshot('session')['objects']==[]
        assert 'state_seq' not in snap  # canonical backend supplies global sequence
        await s.close()
    asyncio.run(run())


def test_overload_retains_only_newest_pending():
    async def run():
        started,release=threading.Event(),threading.Event()
        calls=[]
        def slow(data):
            calls.append(data)
            if len(calls)==1:
                started.set(); assert release.wait(3)
            return []
        s,_=setup(slow)
        s.offer_frame(frame())
        assert await asyncio.to_thread(started.wait,3)
        for seq in range(2,52):
            s.offer_frame(replace(frame(sequence=seq),jpeg=str(seq).encode()))
        assert s.sessions['session'].pending.sequence==51
        release.set()
        await s.sessions['session'].worker
        assert calls==[b'fixture',b'51']
        assert s.snapshot('session')['dropped_frames']==49
        await s.close()
    asyncio.run(run())


@pytest.mark.parametrize('change',['pause','stop','switch','expired'])
def test_inflight_invalidated(change):
    async def run():
        started,release=threading.Event(),threading.Event()
        def slow(_):
            started.set(); assert release.wait(3)
            return [Detection('chair',.9,(0,0,.5,.5))]
        s,now=setup(slow)
        s.offer_frame(frame())
        worker=s.sessions['session'].worker
        assert await asyncio.to_thread(started.wait,3)
        if change=='switch': s.bind('session',2,'real','browser_camera')
        elif change=='expired': now[0]+=1001
        else: s.control('session',change,1)
        release.set(); await worker
        assert s.snapshot('session')['objects']==[]
        await s.close()
    asyncio.run(run())


def test_identity_revision_and_clock_rejection():
    s,_=setup()
    for f in [frame(8000),frame(10001),frame(revision=2),replace(frame(),clock_synced=False)]:
        with pytest.raises(ValueError): s.offer_frame(f)
    with pytest.raises(ValueError): s.control('session','start',0)
    with pytest.raises(ValueError): s.bind('other',1,'real','fixture')
    s.invalidate('session',2)
    assert s.snapshot('session')['status']=='paused'
    with pytest.raises(ValueError): s.offer_frame(frame())


def test_detector_error_unavailable_without_internal_error_leak():
    async def run():
        def broken(_): raise RuntimeError('secret provider error')
        s,_=setup(broken)
        s.offer_frame(frame()); await s.sessions['session'].worker
        snap=s.snapshot('session')
        assert snap['status']=='unavailable' and snap['error']=='detector_failed'
        assert 'secret' not in str(snap)
        await s.close()
    asyncio.run(run())


def test_pause_waiting_for_global_capacity():
    async def run():
        s,_=setup()
        await s.model_lock.acquire()
        s.offer_frame(frame()); worker=s.sessions['session'].worker
        await asyncio.sleep(0)
        s.control('session','pause',1)
        s.model_lock.release(); await worker
        assert s.snapshot('session')['status']=='paused'
        await s.close()
    asyncio.run(run())


def test_close_waits_for_retired_source_worker():
    async def run():
        started,release=threading.Event(),threading.Event()
        def slow(_):
            started.set(); assert release.wait(3)
            return []
        s,_=setup(slow)
        s.offer_frame(frame()); assert await asyncio.to_thread(started.wait,3)
        s.bind('session',2,'real','browser_camera')
        closing=asyncio.create_task(s.close()); await asyncio.sleep(0)
        assert not closing.done()
        release.set(); await closing
        assert not s.sessions and not s.workers
    asyncio.run(run())


def test_slow_callback_does_not_block_model_and_is_cancelled_on_invalidate():
    async def run():
        called=asyncio.Event()
        async def slow(result):
            called.set()
            await asyncio.sleep(100)
        s,_=setup(callback=slow)
        s.offer_frame(frame()); await s.sessions['session'].worker
        await called.wait()
        for seq in range(2,10):
            s.offer_frame(frame(sequence=seq)); await s.sessions['session'].worker
        assert s.snapshot('session')['inferred_frames']==9
        assert s.sessions['session'].offered_candidate['sequence']==9
        assert s.snapshot('session')['callback_drops']>=6
        s.invalidate('session',2)
        await s.close()
    asyncio.run(run())


def test_model_lifecycle_loads_once(monkeypatch):
    async def run():
        loaded=[]
        def loader(path, **kwargs): loaded.append(path); return lambda _: []
        monkeypatch.setattr('app.vision.service.OnnxDetector',loader)
        s=VisionService(SimpleNamespace(LIVE_DETECTOR_MODEL_PATH='model.onnx'))
        await asyncio.gather(s.start(),s.start())
        assert loaded==['model.onnx']
        await s.close()
    asyncio.run(run())


def test_repeated_source_switches_keep_one_session_inference_worker():
    async def run():
        started,release=threading.Event(),threading.Event()
        def slow(_):
            started.set(); assert release.wait(3)
            return [Detection('chair',.9,(.1,.1,.4,.5))]
        s,_=setup(slow)
        s.offer_frame(frame())
        assert await asyncio.to_thread(started.wait,3)
        try:
            for revision in range(2,52):
                s.bind('session',revision,'fixture','fixture')
                s.control('session','start',revision)
                s.offer_frame(frame(revision=revision,sequence=revision))
                await asyncio.sleep(0)
            live_workers=sum(not task.done() for task in s.workers)
            assert live_workers<=1, f'{live_workers} retired inference workers accumulated'
            release.set()
            await s.sessions['session'].worker
            assert s.snapshot('session')['source_revision']==51
            assert s.snapshot('session')['frame_id']=='51'
        finally:
            release.set()
            await s.close()
    asyncio.run(run())
