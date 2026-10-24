import asyncio
import httpx
import pytest
from scripts.simulate_feedback import simulate


def test_simulator_never_uses_physical_routes():
    async def run():
        requests=[]
        def handler(request):
            requests.append(request.url.path)
            if request.url.path=='/status':
                return httpx.Response(200,json={'feedback':{'source':'simulated'},'haptic_event':None})
            return httpx.Response(200,json={'accepted':True})
        async with httpx.AsyncClient(base_url='https://fixture.invalid',transport=httpx.MockTransport(handler)) as client:
            events=await simulate(client,'session','simulator',scenario='clear',cycles=1,interval=0)
        assert len(events)==1
        assert set(requests)=={'/simulation/telemetry','/status'}
        assert events[-1]['source']=='simulated'
    asyncio.run(run())


def test_simulator_fails_on_real_feedback():
    async def run():
        def handler(request):
            return httpx.Response(200,json={'feedback':{'source':'real'}})
        async with httpx.AsyncClient(base_url='https://fixture.invalid',transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(RuntimeError): await simulate(client,'s','d',cycles=1,interval=0)
    asyncio.run(run())
