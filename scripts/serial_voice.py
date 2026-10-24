"""Real ESP32 USB sensor -> macOS speech (uses the system-selected audio output).
Explicit Mac-assisted diagnostic; no automatic avoidance or safe-path inference.
"""
import argparse
import json
import math
import subprocess
import time

PREFIX = b'STRIDE_SENSOR '
PHRASES = {
    'danger': 'Stop. Object nearby.',
    'caution': 'Caution. Object nearby. Stop and check your path.',
    'unknown': 'Distance sensing unavailable. Stop and check.',
    'clear': 'Distance warning cleared. Check your path before moving.',
}


class SensorVoice:
    def __init__(self, speak, timeout=1.0, repeat=5.0):
        self.speak = speak
        self.timeout = timeout
        self.repeat = repeat
        self.last_receipt = None
        self.last_uptime = None
        self.last_distance = None
        self.band = 'unknown'
        self.clear_count = 0
        self.announced = None
        self.last_spoken = float('-inf')

    def receive(self, line, now):
        if not line.startswith(PREFIX) or len(line) > 512:
            return False
        try:
            data = json.loads(line[len(PREFIX):])
            uptime = data['uptime_ms']
            valid = data['measurement_valid']
            distance = data['distance_cm']
            if type(uptime) is not int or uptime < 0 or type(valid) is not bool or data.get('source') != 'real':
                return False
            if self.last_uptime is not None and uptime == self.last_uptime:
                return False  # A repeated line never refreshes sensor health.
            if self.last_uptime is not None and uptime < self.last_uptime:
                self.band = 'unknown'
                self.clear_count = 0
            self.last_uptime = uptime
            gap = self.last_receipt is None or now-self.last_receipt > self.timeout
            self.last_receipt = now
            usable = valid and type(distance) in (int, float) and math.isfinite(distance) and 2 <= distance <= 400
            self.last_distance = distance if usable else None
            previous = 'unknown' if gap else self.band
            if not usable:
                self.band = 'unknown'
                self.clear_count = 0
            elif distance <= 50 or (previous == 'danger' and distance <= 55):
                self.band = 'danger'
                self.clear_count = 0
            elif distance <= 100 or (previous == 'caution' and distance <= 105):
                self.band = 'caution'
                self.clear_count = 0
            elif distance > 105:
                self.clear_count = 1 if gap else self.clear_count+1
                if self.clear_count >= 3:
                    self.band = 'clear'
            else:
                self.clear_count = 0
                self.band = 'caution'
            self.tick(now)
            return True
        except (KeyError, TypeError, ValueError, OverflowError):
            return False

    def tick(self, now):
        if self.last_receipt is None or now-self.last_receipt > self.timeout:
            self.band = 'unknown'
            self.last_distance = None
            self.clear_count = 0
        changed = self.announced != self.band
        repeat = self.band != 'clear' and now-self.last_spoken >= self.repeat
        if changed or repeat:
            # Never announce initial readings as permission to move.
            if self.band != 'clear' or self.announced is not None:
                self.speak(PHRASES[self.band], self.band)
            self.announced = self.band
            self.last_spoken = now


class MacSpeech:
    def __init__(self, mute=False):
        self.process = None
        self.mute = mute

    def __call__(self, phrase, band):
        print(json.dumps({'event': 'voice', 'state': band, 'text': phrase,
                          'source': 'USB sensor / Mac-assisted', 'time': time.time()}), flush=True)
        self.close()
        if not self.mute:
            self.process = subprocess.Popen(['/usr/bin/say', '-r', '190', phrase])

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=.2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None


def main():
    import serial
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--mute', action='store_true')
    parser.add_argument('--seconds', type=float, default=0)
    args = parser.parse_args()
    speech = MacSpeech(args.mute)
    policy = SensorVoice(speech)
    started = time.monotonic()
    print('USB/Mac-assisted voice. Ctrl-C stops. No left/right avoidance instructions. No images or audio recorded.', flush=True)
    try:
        # One serial owner only. Opening may reset the board; allow startup time.
        with serial.Serial(args.port, 115200, timeout=.05) as connection:
            connection.reset_input_buffer()
            ready_at = time.monotonic()+3
            buffer = bytearray()
            last_display = 0
            while not args.seconds or time.monotonic()-started < args.seconds:
                # Bound input; retain partial lines across serial timeouts.
                chunk = connection.read(min(max(connection.in_waiting, 1), 4096))
                now = time.monotonic()
                buffer.extend(chunk)
                lines = buffer.split(b'\n')
                buffer = bytearray(lines.pop())
                # Only newest complete sensor line matters; discard any backlog.
                candidates = [line.strip() for line in lines if line.startswith(PREFIX) and len(line) <= 512]
                if candidates:
                    policy.receive(candidates[-1], now)
                if len(buffer) > 512:
                    buffer.clear()
                if now >= ready_at:
                    policy.tick(now)
                if now-last_display >= .5:
                    last_display = now
                    print(json.dumps({'event': 'sensor', 'state': policy.band,
                                      'distance_cm': policy.last_distance,
                                      'source': 'USB sensor / Mac-assisted'}), flush=True)
    except (serial.SerialException, OSError) as error:
        speech(PHRASES['unknown'], 'unknown')
        print(f'Serial connection unavailable: {error}', flush=True)
        if speech.process:
            speech.process.wait(timeout=10)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        speech.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
