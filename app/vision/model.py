"""YOLOv8 detection ONNX decoder. No training/export dependency on serving path."""
import ast
import io
import hashlib
from time import perf_counter
from pathlib import Path
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageOps


@dataclass(frozen=True)
class Detection:
    label: str
    score: float
    # Canonical box: [xmin, ymin, xmax, ymax], floats 0..1.
    box: tuple[float, float, float, float]


def iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, y2-y1) * max(0, x2-x1)
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union if union > 0 else 0


def read_jpeg(data):
    if not data or len(data) > 1_000_000:
        raise ValueError('JPEG must be 1..1000000 bytes')
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'JPEG':
            raise ValueError('Only JPEG frames are accepted')
        w, h = image.size
        if max(w, h) > 1920 or w*h > 1920*1080:
            raise ValueError('Image exceeds pixel limits')
        return ImageOps.exif_transpose(image).convert('RGB')


def preprocess(image, size):
    w, h = image.size
    gain = min(size / w, size / h)
    nw, nh = round(w * gain), round(h * gain)
    left, top = round((size-nw)/2 - .1), round((size-nh)/2 - .1)
    canvas = Image.new('RGB', (size, size), (114, 114, 114))
    canvas.paste(image.resize((nw, nh), Image.Resampling.BILINEAR), (left, top))
    tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255
    return tensor, (gain, left, top, w, h)


class OnnxDetector:
    def __init__(self, path, confidence=.35, nms_iou=.45, threads=2, expected_sha256=None):
        if expected_sha256 and hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected_sha256:
            raise ValueError("Model artifact checksum mismatch")
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        self.session = ort.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])
        inp = self.session.get_inputs()[0]
        if inp.type != 'tensor(float)' or len(inp.shape) != 4 or inp.shape[:2] != [1, 3] or inp.shape[2] != inp.shape[3] or not isinstance(inp.shape[2], int):
            raise ValueError('Require static float32 [1,3,S,S] YOLOv8 detection export')
        self.input_name, self.size = inp.name, inp.shape[2]
        metadata = self.session.get_modelmeta().custom_metadata_map
        names = ast.literal_eval(metadata['names'])
        self.names = names if isinstance(names, dict) else dict(enumerate(names))
        if set(self.names) != set(range(len(self.names))):
            raise ValueError('Model labels must have contiguous integer IDs')
        self.confidence, self.nms_iou = confidence, nms_iou

    def __call__(self, jpeg):
        return self.profile(jpeg)[0]

    def profile(self, jpeg):
        # No frames/tensors are retained by profiling; only stage durations.
        started = perf_counter()
        image = read_jpeg(jpeg)
        decoded = perf_counter()
        tensor, geometry = preprocess(image, self.size)
        preprocessed = perf_counter()
        raw = self.session.run(None, {self.input_name: tensor})[0]
        inferred = perf_counter()
        detections = self.decode(raw, geometry)
        completed = perf_counter()
        return detections, {'jpeg_decode_ms': (decoded-started)*1000,
                            'preprocess_ms': (preprocessed-decoded)*1000,
                            'inference_ms': (inferred-preprocessed)*1000,
                            'postprocess_ms': (completed-inferred)*1000,
                            'detector_ms': (completed-started)*1000}


    def decode(self, raw, geometry):
        if raw.ndim != 3 or raw.shape[:2] != (1, 4+len(self.names)):
            raise ValueError('Unexpected YOLOv8 output; require [1,4+classes,anchors], nms=False')
        gain, left, top, w, h = geometry
        rows = raw[0].T
        rows = rows[np.isfinite(rows).all(axis=1)]
        # Select class/score for every anchor in NumPy, then decode only eligible
        # boxes. YOLOv8n at 320 has 2100 anchors, usually only a few survive.
        classes = rows[:,4:].argmax(axis=1)
        scores = rows[np.arange(len(rows)),4+classes].astype(np.float64,copy=False)
        eligible = np.flatnonzero((scores>=self.confidence) & (scores<=1))
        candidates = []
        for index in eligible:
            row = rows[index]
            cls = int(classes[index])
            score = float(scores[index])
            cx, cy, bw, bh = row[:4]
            x1, y1 = max(0., (cx-bw/2-left)/gain/w), max(0., (cy-bh/2-top)/gain/h)
            x2, y2 = min(1., (cx+bw/2-left)/gain/w), min(1., (cy+bh/2-top)/gain/h)
            box = tuple(float(v) for v in (x1, y1, x2, y2))
            if box[0] < box[2] and box[1] < box[3]:
                candidates.append(Detection(self.names[cls], score, box))
        kept = []
        for item in sorted(candidates, key=lambda x: x.score, reverse=True):
            if not any(item.label == other.label and iou(item.box, other.box) > self.nms_iou for other in kept):
                kept.append(item)
            if len(kept) == 100:
                break
        return kept
