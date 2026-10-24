"""Compare original/exported raw tensors on identical preprocessed JPEG inputs."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from ultralytics import YOLO
from app.vision.model import OnnxDetector, preprocess, read_jpeg

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('images', nargs='+')
parser.add_argument('--output', default='qa/export-comparison.json')
args = parser.parse_args()
reference = YOLO('models/yolov8n.pt').model.eval().fuse()
exported = OnnxDetector('models/yolov8n.onnx')
reports = []
for name in args.images:
    data = Path(name).read_bytes()
    tensor, geometry = preprocess(read_jpeg(data), exported.size)
    with torch.no_grad():
        raw = reference(torch.from_numpy(tensor))[0].numpy()
    onnx = exported.session.run(None, {exported.input_name:tensor})[0]
    # Small absolute error is expected in decoded pixel coordinates on CPU.
    np.testing.assert_allclose(onnx,raw,rtol=.001,atol=.002)
    a,b = exported.decode(raw,geometry),exported.decode(onnx,geometry)
    assert [x.label for x in a] == [x.label for x in b]
    assert all(max(abs(v-w) for v,w in zip(x.box,y.box))<=.001 for x,y in zip(a,b))
    reports.append({'fixture':Path(name).name,'max_abs_error':float(np.max(np.abs(onnx-raw))),
                    'detections':len(a),'labels':[x.label for x in a],'status':'PASS'})
Path(args.output).write_text(json.dumps(reports,indent=2)+'\n')
print(json.dumps(reports,indent=2))
