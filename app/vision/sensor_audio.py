"""USB sensor priority for the local Mac webcam demo, not hosted navigation."""
import time
from scripts.serial_voice import SensorVoice, MacSpeech, PREFIX


class SensorAudio:
    def __init__(self, port, preview, *, connection=None, speech=None, clock=time.monotonic):
        import serial
        self.connection = connection if connection is not None else serial.Serial(port, 115200, timeout=0)
        self.preview = preview
        self.speech = speech if speech is not None else MacSpeech()
        self.clock = clock
        self.policy = SensorVoice(self._announce)
        self.buffer = bytearray()
        self.failed = False

    def _announce(self, phrase, band):
        self.preview.stop()  # Sensor warnings interrupt object narration.
        self.speech(phrase, band)

    def poll(self):
        import serial
        if not self.failed:
            try:
                count = min(self.connection.in_waiting, 4096)
                if count:
                    self.buffer.extend(self.connection.read(count))
                    lines = self.buffer.split(b'\n')
                    self.buffer = bytearray(lines.pop())
                    valid = [line.strip() for line in lines if line.startswith(PREFIX) and len(line) <= 512]
                    if valid:
                        self.policy.receive(valid[-1], self.clock())
                    if len(self.buffer) > 512:
                        self.buffer.clear()
            except (serial.SerialException, OSError):
                self.failed = True
                self.policy.last_receipt = None
        self.policy.tick(self.clock())
        if self.policy.band != 'clear':
            self.preview.stop()

    @property
    def allow_observation(self):
        process = self.speech.process
        return self.policy.band == 'clear' and (process is None or process.poll() is not None)

    def close(self):
        self.speech.close()
        self.connection.close()
