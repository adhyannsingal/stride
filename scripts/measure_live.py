"""Local continuous detector measurement; webcam or explicitly labeled file fixture.
Run from repo root: PYTHONPATH=. python scripts/measure_live.py --seconds 60
"""
import argparse
import asyncio
import json
import hashlib
from collections import Counter, defaultdict, deque
import resource
import sys
import time
from pathlib import Path
from uuid import uuid4
import cv2
import numpy as np
from app.vision.model import OnnxDetector
from app.vision.capture import encode_capture
from app.vision.service import Frame, VisionService, epoch_ms


async def measure(args):
    source = 'fixture' if args.file else 'real'
    origin = 'fixture' if args.file else 'browser_camera'
    model_hash=hashlib.sha256(Path(args.model).read_bytes()).hexdigest()
    model = OnnxDetector(args.model, threads=args.threads)
    stages = defaultdict(lambda: deque(maxlen=10000))
    labels = Counter()
    empty_frames = [0]
    def detector(jpeg):
        objects, timings = model.profile(jpeg)
        labels.update(item.label for item in objects)
        empty_frames[0] += not objects
        for key, value in timings.items():
            stages[key].append(value)
        return objects
    service = VisionService(detector=detector)
    service.bind('local-measurement', 1, source, origin)
    service.control('local-measurement', 'start', 1)
    cap = None if args.file else cv2.VideoCapture(args.camera)
    if cap is not None:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not cap.isOpened():
            raise RuntimeError('Webcam unavailable; no fallback selected. Grant camera access or explicitly use --file.')
    jpeg = Path(args.file).read_bytes() if args.file else None
    ages, completed, seq, last = [], 0, 0, None
    capture_rejections = 0
    dark_frames = 0
    dimensions = None
    failure = None
    start = time.monotonic()
    next_capture = start
    try:
        while time.monotonic()-start < args.seconds:
            if time.monotonic() >= next_capture:
                capture_started = time.perf_counter()
                captured = epoch_ms()
                if cap is not None:
                    ok, image = await asyncio.to_thread(cap.read)
                    if not ok:
                        raise RuntimeError('Webcam read failed')
                    jpeg, dimensions, quality = encode_capture(image)
                    dark_frames += quality['nearly_black']
                    stages['capture_encode_ms'].append((time.perf_counter()-capture_started)*1000)
                seq += 1
                try:
                    service.offer_frame(Frame('local-measurement', 'local-camera', 'measurement-boot', seq,
                                         str(uuid4()), captured, 1, source, origin, jpeg))
                except ValueError:
                    capture_rejections += 1  # Startup/slow capture is dropped, never restamped fresh.
                next_capture = max(next_capture+1/args.hz, time.monotonic())
            result = service.snapshot('local-measurement')
            if result['frame_id'] and result['frame_id'] != last:
                last = result['frame_id']
                completed += 1
                ages.append(result['completed_ms']-result['captured_ms'])
            await asyncio.sleep(.005)
    except Exception as exc:
        failure = type(exc).__name__ + ': ' + str(exc)
    finally:
        if cap is not None:
            cap.release()
        final = service.snapshot('local-measurement')
        await service.close()
    elapsed = time.monotonic()-start
    report = {'source': source, 'origin': origin, 'model_sha256': model_hash,
              'encoded_dimensions':dimensions,'nearly_black_frames':dark_frames,
              'scene_check':'BLOCKED (nearly black input)' if seq and dark_frames/seq>.9 else 'NOT RUN (no controlled ground truth)',
              'threads': args.threads, 'observed_labels':dict(labels), 'empty_inferred_frames':empty_frames[0],
              'stage_ms':{key:{name:float(np.percentile(values,p)) for name,p in [('p50',50),('p95',95),('max',100)]} for key,values in stages.items()},
              'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if sys.platform=='darwin' else 1024), 'duration_s': round(elapsed,3),
              'error': failure, 'capture_rejections': capture_rejections, 'capture_hz': seq/elapsed, 'returned_result_hz': completed/elapsed,
              'inferred_frames': final['inferred_frames'], 'dropped_frames': final['dropped_frames'],
              'unique_results': completed, 'age_ms': {key: float(np.percentile(ages,p)) if ages else None
                    for key,p in [('p50',50),('p95',95),('max',100)]},
              'performance_gate': 'NOT RUN (fixture)' if args.file else 'PASS' if failure is None and elapsed >= args.seconds and completed/elapsed>=5 and ages and np.percentile(ages,95)<=500 else 'FAIL',
              'scope': 'local detector; excludes hosted transport, phone speech and W11'}
    print(json.dumps(report,indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='models/yolov8n.onnx')
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--file', help='Explicit fixture JPEG; never counts as live acceptance')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--hz', type=float, default=6)
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.seconds<=0 or args.hz<=0 or args.threads<1:
        parser.error('seconds and hz must be positive')
    asyncio.run(measure(args))
