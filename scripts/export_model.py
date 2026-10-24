"""Development only: export pinned YOLOv8n and write auditable manifest."""
import hashlib
import json
from pathlib import Path
import importlib.metadata
import urllib.request
from ultralytics import YOLO

root = Path('models')
root.mkdir(exist_ok=True)
checkpoint=root/'yolov8n.pt'
checkpoint_url='https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n.pt'
expected='f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36'
if not checkpoint.exists():
    with urllib.request.urlopen(checkpoint_url,timeout=30) as response:
        checkpoint.write_bytes(response.read(10_000_000))
if hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=expected:
    raise RuntimeError('Pinned checkpoint checksum mismatch; refusing to load')
model = YOLO(str(checkpoint))
output = Path(model.export(format='onnx', imgsz=320, opset=17, simplify=False,
                         dynamic=False, nms=False, batch=1, device='cpu'))
manifest = {'checkpoint_url':checkpoint_url,'license':'https://github.com/ultralytics/ultralytics/blob/main/LICENSE',
            'checkpoint': 'yolov8n.pt', 'onnx_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'checkpoint_sha256': hashlib.sha256((root/'yolov8n.pt').read_bytes()).hexdigest(),
            'input': [1,3,320,320], 'output': '[1,84,2100]', 'labels': model.names,
            'preprocessing': 'RGB, letterbox 114, float32 /255, BCHW; no mirror',
            'box': '[xmin,ymin,xmax,ymax] floats 0..1, upright unmirrored image',
            'decoder': 'cxcywh pixels + 80 class scores; no objectness; class-aware NMS IoU .45; score >= .35',
            'versions': {name: importlib.metadata.version(name) for name in ['ultralytics','torch','onnx','onnxruntime']}}
(root/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
print(output)
