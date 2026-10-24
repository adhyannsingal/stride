import json
from scripts.serial_voice import SensorVoice, PREFIX


def packet(uptime, distance=150, valid=True):
    return PREFIX+json.dumps(dict(uptime_ms=uptime, distance_cm=distance,
                                  measurement_valid=valid, source='real')).encode()


def test_stop_interrupts_clear_and_stale_cannot_resume():
    spoken=[]
    p=SensorVoice(lambda text,band:spoken.append((text,band)))
    for i in range(3): p.receive(packet(i*100),i*.1)
    assert p.band=='clear'
    p.receive(packet(300,20),.3)
    assert spoken[-1]==('Stop. Object nearby.','danger')
    p.tick(1.4)
    assert spoken[-1][1]=='unknown'
    # Duplicate data cannot restore or refresh a stale sensor.
    assert not p.receive(packet(300,20),1.5)
    assert p.band=='unknown'
    for i in range(2): p.receive(packet(400+i*100),1.6+i*.1)
    assert p.band=='unknown'
    p.receive(packet(600),1.8)
    assert p.band=='clear' and 'before moving' in spoken[-1][0]
    assert not any('move left' in text.lower() or 'move right' in text.lower() for text,_ in spoken)


def test_invalid_no_echo_repeat_hysteresis_and_restart():
    spoken=[]
    p=SensorVoice(lambda text,band:spoken.append((text,band)))
    p.receive(packet(100,20),0)
    p.receive(packet(200,53),.1)
    assert p.band=='danger'
    p.receive(packet(300,None,False),.2)
    assert p.band=='unknown'
    size=len(spoken)
    p.tick(.5)
    assert len(spoken)==size
    p.tick(6)
    assert len(spoken)==size+1
    for i in range(3): p.receive(packet(400+i*100),7+i*.1)
    assert p.band=='clear'
    p.receive(packet(10),7.3)
    assert p.band=='unknown'
    p.receive(packet(11,float('nan')),7.4)
    assert p.band=='unknown'
    assert not p.receive(PREFIX+b'{}',8)
