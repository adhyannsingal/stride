"""Explicit simulation client. Never calls physical telemetry/command endpoints."""
import argparse
import asyncio
import json
import os
import time
from uuid import uuid4
import httpx

SCENARIOS = {'clear':(120.,True,'none'),'warning':(80.,True,'warning'),
             'urgent':(20.,True,'urgent'),'invalid':(None,False,'sensor_fault')}


async def simulate(client, session_id, device_id, scenario='demo', cycles=5, interval=.2):
    boot,sequence,started=str(uuid4()),0,time.monotonic()
    names=list(SCENARIOS)+['stale','reboot'] if scenario=='demo' else [scenario]
    ack_delay=2.0 if scenario=='ack-delay' else 0
    if scenario=='ack-delay': names=['clear']
    events=[]
    seen=set()
    for name in names:
        if name=='stale':
            await asyncio.sleep(1.2)
            reply=await client.get('/status',params={'session_id':session_id})
            reply.raise_for_status()
            events.append({'scenario':'stale','status':reply.json()})
            continue
        if name=='reboot':
            boot=str(uuid4()); sequence=0
            name='clear'
        for _ in range(cycles):
            sequence+=1
            distance,valid,alert=SCENARIOS[name]
            payload={'session_id':session_id,'device_id':device_id,'boot_id':boot,
                     'sequence':sequence,'uptime_ms':round((time.monotonic()-started)*1000),
                     'distance_cm':distance,'valid':valid,'local_alert':alert,'active_command_id':None}
            reply=await client.post('/simulation/telemetry',json=payload)
            reply.raise_for_status()
            request_started=time.monotonic()
            status=await client.get('/status',params={'session_id':session_id})
            status.raise_for_status()
            state=status.json()
            if state.get('feedback',{}).get('source')!='simulated':
                raise RuntimeError('Backend did not identify simulated feedback; refusing to continue')
            event=state.get('haptic_event')
            if event and event.get('command_id') and event['command_id'] not in seen:
                required={'command_id','generation','remaining_ttl_ms'}
                if not required <= event.keys():
                    raise RuntimeError('Backend simulated haptic event lacks canonical command/ACK fields')
                seen.add(event['command_id'])
                if ack_delay: await asyncio.sleep(ack_delay)
                elapsed_ms=(time.monotonic()-request_started)*1000
                ack={'session_id':session_id,'device_id':device_id,'boot_id':boot,
                     'command_id':event['command_id'],'generation':event['generation'],
                     'status':'accepted' if elapsed_ms<event['remaining_ttl_ms']<=1500 else 'expired'}
                response=await client.post('/simulation/ack',json=ack)
                response.raise_for_status()
                if ack['status']=='accepted':
                    # This means simulator completion only, never physical output.
                    response=await client.post('/simulation/ack',json=dict(ack,status='completed'))
                    response.raise_for_status()
            events.append({'scenario':name,'sequence':sequence,'source':'simulated',
                           'feedback':state['feedback']})
            await asyncio.sleep(interval)
    return events


async def main(a):
    cookie=os.environ.get('STRIDE_UI_COOKIE')
    if not cookie: raise RuntimeError('Set STRIDE_UI_COOKIE privately; developer simulation session required')
    if not a.base_url.startswith(('https://','http://127.0.0.1:','http://localhost:')):
        raise RuntimeError('Use HTTPS or loopback')
    async with httpx.AsyncClient(base_url=a.base_url,headers={'Cookie':cookie},timeout=3) as client:
        result=await simulate(client,a.session_id,a.device_id,a.scenario)
        print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',required=True); p.add_argument('--session-id',required=True)
    p.add_argument('--device-id',default='simulator-1')
    p.add_argument('--scenario',choices=['demo','stale','reboot','ack-delay',*SCENARIOS],default='demo')
    asyncio.run(main(p.parse_args()))
