from app.vision.model import Detection
from app.vision.preview_audio import PreviewAudio


class Process:
    def __init__(self): self.running = True; self.cancelled = False
    def poll(self): return None if self.running else 0
    def terminate(self): self.running = False; self.cancelled = True
    def wait(self, timeout): self.running = False


def setup():
    now, spoken, processes = [10.0], [], []
    def spawn(text):
        spoken.append(text); processes.append(Process()); return processes[-1]
    audio = PreviewAudio(spawn=spawn, clock=lambda: now[0])
    return audio, now, spoken, processes


CHAIR = Detection('chair', .9, (.4,.1,.6,.9))
CUP = Detection('cup', .8, (.05,.1,.2,.6))


def frame(audio, now, objects, advance=.1):
    now[0] += advance
    return audio.update(objects, now[0]-.03)


def test_requires_consistent_frames_and_does_not_repeat_a_persistent_object():
    audio, now, spoken, processes = setup()
    assert frame(audio, now, [CHAIR]) is None
    assert frame(audio, now, [CHAIR]) == 'chair, ahead.'
    processes[-1].running = False
    for _ in range(40): frame(audio, now, [CHAIR])
    assert spoken == ['chair, ahead.']


def test_busy_speech_does_not_queue_but_other_stable_object_can_speak_later():
    audio, now, spoken, processes = setup()
    frame(audio, now, [CHAIR, CUP]); frame(audio, now, [CHAIR, CUP])
    frame(audio, now, [CHAIR, CUP])
    assert spoken == ['chair, ahead.']
    processes[0].running = False
    frame(audio, now, [CHAIR, CUP])
    assert spoken == ['chair, ahead.', 'cup, to the left.']
    assert all('move' not in text and 'turn' not in text for text in spoken)


def test_stale_or_invalid_input_cancels_audio_and_resets_stabilization():
    audio, now, spoken, processes = setup()
    frame(audio, now, [CHAIR]); frame(audio, now, [CHAIR])
    assert audio.update([CHAIR], now[0]-1) is None
    assert processes[0].cancelled
    assert frame(audio, now, [CHAIR]) is None
    assert audio.update([CHAIR], now[0], valid=False) is None
    assert len(spoken) == 1


def test_expiry_stops_current_process_without_waiting_for_another_detection():
    audio, now, spoken, processes = setup()
    frame(audio, now, [CHAIR]); frame(audio, now, [CHAIR])
    now[0] += 1
    audio.tick()
    assert processes[0].cancelled and audio.process is None


def test_pause_and_lost_scene_cancel_only_owned_speech():
    audio, now, spoken, processes = setup()
    frame(audio, now, [CHAIR]); frame(audio, now, [CHAIR])
    frame(audio, now, [])
    assert processes[0].cancelled
    frame(audio, now, [CUP]); frame(audio, now, [CUP])
    audio.stop()
    assert processes[-1].cancelled
    assert audio.process is None and not audio.announced
