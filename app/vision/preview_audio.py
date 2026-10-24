"""Opt-in Mac speech for the local preview, not the navigation speech arbiter."""
from pathlib import Path
import subprocess
import time

from .tracking import Tracker


def mac_speech(text):
    if not Path('/usr/bin/say').is_file():
        raise RuntimeError('Preview speech requires macOS /usr/bin/say; omit --speak elsewhere')
    # Text goes through stdin; no shell or model-derived command arguments.
    process = subprocess.Popen(['/usr/bin/say', '-r', '220'], stdin=subprocess.PIPE,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        process.stdin.write((text + '\n').encode('utf-8'))
        process.stdin.close()
    except OSError:
        process.terminate()
        process.wait(timeout=1)
        raise
    return process


class PreviewAudio:
    """Two-frame stabilization, no speech queue, current-frame expiry and cleanup.

    Only describes image location. No move/turn/clear-path instruction is emitted.
    Capture, inference and this clock must share the local monotonic timebase.
    """
    def __init__(self, spawn=mac_speech, clock=time.monotonic):
        self.spawn, self.clock = spawn, clock
        self.tracker = Tracker()
        self.process = None
        self.expires = 0
        self.announced = set()
        self.cooldowns = {}

    def _cancel_process(self):
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=.1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=.1)

    def tick(self):
        if self.process is not None:
            if self.clock() >= self.expires:
                self._cancel_process()
            elif self.process.poll() is not None:
                self.process = None

    def stop(self):
        self._cancel_process()
        self.tracker = Tracker()
        self.announced.clear()
        self.cooldowns.clear()

    def update(self, detections, captured_at, valid=True):
        now = self.clock()
        self.tick()
        if not valid or not 0 <= now - captured_at < 1:
            self.stop()
            return None
        objects, _ = self.tracker.update(detections, int(now * 1000))
        present = {(obj['track_id'], obj['position']) for obj in objects}
        self.announced.intersection_update(present)
        self.cooldowns = {key: stamp for key, stamp in self.cooldowns.items() if now-stamp < 3}
        if not objects:
            self._cancel_process()
        if self.process is not None:
            return None  # Continue tracking; never build a narration backlog.
        objects.sort(key=lambda obj: (obj['position'] != 'center', -obj['score']))
        for obj in objects:
            key = (obj['track_id'], obj['position'])
            cooldown = (obj['label'], obj['position'])
            if (self.tracker.tracks[obj['track_id']]['count'] < 2
                    or key in self.announced or cooldown in self.cooldowns):
                continue
            location = 'ahead' if obj['position'] == 'center' else f"to the {obj['position']}"
            text = f"{obj['label']}, {location}."
            self.process = self.spawn(text)
            self.expires = captured_at + 1
            self.announced.add(key)
            self.cooldowns[cooldown] = now
            return text
        return None
