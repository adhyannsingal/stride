import json
from app.vision.sensor_audio import SensorAudio
from scripts.serial_voice import PREFIX


class Port:
    data=b''
    fail=False
    @property
    def in_waiting(self):
        if self.fail: raise OSError('unplugged')
        return len(self.data)
    def read(self,n):
        data,self.data=self.data[:n],self.data[n:]
        return data
    def close(self): pass


class Speech:
    process=None
    def __init__(self): self.events=[]
    def __call__(self,text,band): self.events.append(band)
    def close(self): pass


class Preview:
    def __init__(self): self.stops=0
    def stop(self): self.stops+=1


def test_real_serial_format_prioritizes_warning_and_disconnect_over_objects():
    now=[0.0]
    port,voice,preview=Port(),Speech(),Preview()
    sensor=SensorAudio('unused',preview,connection=port,speech=voice,clock=lambda:now[0])
    def send(uptime,cm):
        port.data=PREFIX+json.dumps(dict(uptime_ms=uptime,measurement_valid=True,distance_cm=cm,source='real')).encode()+b'\n'
        now[0]+=.1; sensor.poll()
    for i in range(3): send(i*100,150)
    assert sensor.allow_observation
    count=preview.stops
    send(300,20)
    assert not sensor.allow_observation and voice.events[-1]=='danger'
    assert preview.stops>count
    port.fail=True
    sensor.poll()
    assert not sensor.allow_observation and voice.events[-1]=='unknown'
    sensor.close()
