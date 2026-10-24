"""Compare CPU thread counts on identical transient real webcam frames.
No photos are stored; this measures latency/consistency, not object accuracy.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import cv2
import numpy as np
from app.vision.model import OnnxDetector, iou
from app.vision.capture import encode_capture


def same_detections(a,b):
    if len(a)!=len(b): return False
    unmatched=list(b)
    for item in a:
        matches=[(iou(item.box,other.box),i) for i,other in enumerate(unmatched)
                 if item.label==other.label and abs(item.score-other.score)<.005]
        overlap,index=max(matches,default=(0,None))
        if overlap<.99: return False
        unmatched.pop(index)
    return True


def tune(args):
    models={threads:OnnxDetector(args.model,threads=threads) for threads in args.threads}
    cap=cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
    stages={t:defaultdict(list) for t in models}
    labels=Counter(); disagreements=0; dark_frames=0
    try:
        for index in range(args.samples+5):
            ok,frame=cap.read()
            if not ok: raise RuntimeError('Real webcam read failed; no fixture fallback')
            payload,_,quality=encode_capture(frame)
            dark_frames+=quality['nearly_black']
            order=list(models)
            order=order[index%len(order):]+order[:index%len(order)]
            predictions={}
            for threads in order:
                found,timings=models[threads].profile(payload)
                predictions[threads]=found
                if index>=5:
                    for name,value in timings.items(): stages[threads][name].append(value)
            reference=predictions[args.threads[0]]
            if index>=5:
                labels.update(d.label for d in reference)
                disagreements+=sum(not same_detections(reference,other) for other in predictions.values())
    finally:
        cap.release()
    summary={t:{name:{'p50':float(np.percentile(values,50)),'p95':float(np.percentile(values,95))}
                for name,values in groups.items()} for t,groups in stages.items()}
    best=min(summary,key=lambda t:summary[t]['detector_ms']['p95'])
    # Keep the existing two-thread baseline when an apparent gain is just noise.
    baseline=summary[2]['detector_ms']['p95'] if 2 in summary else float('inf')
    chosen=best if summary[best]['detector_ms']['p95']<baseline*.9 else 2
    report={'source':'real','origin':'browser_camera','capture_adapter':'opencv_webcam','model_sha256':hashlib.sha256(Path(args.model).read_bytes()).hexdigest(),
            'samples_per_config':args.samples,'warmup_frames':5,'observed_labels':dict(labels),
            'nearly_black_frames':dark_frames,'detection_disagreements':disagreements,'stage_ms_by_threads':summary,
            'selected_threads':chosen,'selection_rule':'lowest p95, requiring >=10% gain over two threads',
            'scope':'local M4 CPU latency comparison; not hosted capacity or scene accuracy',
            'status':'PASS' if disagreements==0 else 'FAIL'}
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',default='models/yolov8n.onnx')
    p.add_argument('--threads',nargs='+',type=int,default=[1,2,4])
    p.add_argument('--samples',type=int,default=45)
    p.add_argument('--camera',type=int,default=0)
    p.add_argument('--output',default='qa/webcam-thread-tuning.json')
    args=p.parse_args()
    if args.samples<10 or 2 not in args.threads or min(args.threads)<1:
        p.error('Use >=10 samples and positive thread counts including baseline 2')
    tune(args)
