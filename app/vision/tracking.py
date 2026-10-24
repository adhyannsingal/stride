"""Class/IoU matching; stable IDs and bounded announcement frequency."""
from uuid import uuid4
from .model import iou


class Tracker:
    def __init__(self):
        self.tracks = {}
        self.last_spoken = {}

    def update(self, detections, now):
        old = self.tracks
        current, objects, speech = {}, [], None
        for det in detections:
            matches = [(iou(det.box, t['box']), key) for key, t in old.items()
                       if t['label'] == det.label and now-t['seen'] <= 1000]
            match = max(matches, default=(0, None))
            key = match[1] if match[0] >= .3 else str(uuid4())
            previous = old.pop(key, None)
            center = (det.box[0]+det.box[2])/2
            position = 'left' if center < 1/3 else 'right' if center > 2/3 else 'center'
            count = previous['count']+1 if previous else 1
            spoken = previous['spoken'] if previous else None
            current[key] = {'label': det.label, 'box': det.box, 'seen': now, 'count': count, 'spoken': spoken}
            objects.append({'track_id': key, 'label': det.label, 'score': det.score,
                            'box': list(det.box), 'position': position})
            cooldown_key = (det.label, position)
            if speech is None and count >= 2 and spoken != position and now-self.last_spoken.get(cooldown_key, -3000) >= 3000:
                current[key]['spoken'] = position
                self.last_spoken[cooldown_key] = now
                speech = {'event_id': str(uuid4()), 'kind': 'vision_candidate', 'priority': 'observation',
                          'text': f'{det.label}, {position} of camera view.', 'created_ms': now, 'expires_ms': now+1000}
        self.tracks = current
        self.last_spoken = {k: v for k, v in self.last_spoken.items() if now-v < 3000}
        return objects, speech
