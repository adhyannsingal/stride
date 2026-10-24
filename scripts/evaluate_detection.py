"""Offline evaluation on human-reviewed local JPEGs; never labels itself live.
Run with a manifest following qa/quality/manifest.example.json. No image download,
training, auto-labeling or runtime threshold changes are performed.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
from app.vision.model import OnnxDetector, iou


def valid_box(box):
    return (isinstance(box,(list,tuple)) and len(box)==4
            and all(type(x) in {int,float} and math.isfinite(x) and 0<=x<=1 for x in box)
            and box[0]<box[2] and box[1]<box[3])


def match_predictions(truth,predictions,threshold,match_iou=.5):
    unmatched=set(range(len(truth))); tp=[]; fp=[]
    for prediction in sorted(predictions,key=lambda p:p['score'],reverse=True):
        if prediction['score']<threshold: continue
        matches=[(iou(prediction['box'],truth[i]['box']),i) for i in unmatched
                 if truth[i]['label']==prediction['label']]
        overlap,index=max(matches,default=(0,None))
        if overlap>=match_iou:
            unmatched.remove(index); tp.append(prediction['label'])
        else: fp.append(prediction['label'])
    return {'tp':tp,'fp':fp,'fn':[truth[i]['label'] for i in sorted(unmatched)]}


def metrics(counts):
    tp,fp,fn=(counts.get(k,0) for k in ['tp','fp','fn'])
    return dict(tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else None,
                recall=tp/(tp+fn) if tp+fn else None)


def validate_manifest(manifest):
    labels=manifest.get('labels')
    if not labels or len(set(labels))!=len(labels) or any(not isinstance(x,str) or not x.strip() for x in labels):
        raise ValueError('Declare a nonempty unique evaluation label list')
    samples=manifest.get('images',[])
    if not samples: raise ValueError('No reviewed images provided')
    ids=set(); groups={}; splits=set()
    for image in samples:
        if not image.get('id') or image['id'] in ids: raise ValueError('Unique image IDs required')
        ids.add(image['id'])
        if image.get('reviewed') is not True or image.get('complete_for_labels') is not True:
            raise ValueError('Every image needs human review and complete annotations for evaluation labels')
        split=image.get('split')
        if split not in {'tuning','validation'}: raise ValueError('Use tuning or validation split')
        splits.add(split)
        scene=image.get('scene_id')
        if not scene: raise ValueError('scene_id required to keep related images in one split')
        if scene in groups and groups[scene]!=split: raise ValueError('Scene leaks between tuning and validation')
        groups[scene]=split
        if 'objects' not in image: raise ValueError('objects required; [] is a reviewed negative scene')
        for obj in image['objects']:
            if obj.get('label') not in labels or not valid_box(obj.get('box')):
                raise ValueError('Invalid annotation label or normalized XYXY box')
    if splits!={'tuning','validation'}: raise ValueError('Separate tuning and held-out validation images required')


def evaluate(manifest,predictions,thresholds,match_iou=.5):
    validate_manifest(manifest)
    if not 0<match_iou<=1 or not thresholds or any(not 0<=t<=1 for t in thresholds):
        raise ValueError('Invalid confidence or IoU threshold')
    result={}
    for threshold in thresholds:
        splits={}
        for split in ['tuning','validation']:
            counts=defaultdict(int); classes={label:defaultdict(int) for label in manifest['labels']}; failures=[]
            for sample in manifest['images']:
                if sample['split']!=split: continue
                raw=predictions[sample['id']]
                for pred in raw:
                    if not valid_box(pred.get('box')) or not isinstance(pred.get('score'),(int,float)) or not math.isfinite(pred['score']) or not 0<=pred['score']<=1:
                        raise ValueError('Invalid detector prediction')
                selected=[p for p in raw if p['label'] in classes]
                matches=match_predictions(sample['objects'],selected,threshold,match_iou)
                for kind,labels in matches.items():
                    counts[kind]+=len(labels)
                    for label in labels: classes[label][kind]+=1
                if matches['fp'] or matches['fn']:
                    failures.append({'image_id':sample['id'],'false_positive_labels':matches['fp'],
                                     'missed_labels':matches['fn'],'conditions':sample.get('conditions',[])})
            splits[split]=dict(overall=metrics(counts),per_class={k:metrics(v) for k,v in classes.items()},failures=failures)
        result[str(threshold)]=splits
    return {'scope':'offline human-reviewed image evaluation; not live/navigation validation',
            'matching':'score-ordered, same-class, one-to-one IoU matching', 'iou_threshold':match_iou,
            'evaluation_labels':manifest['labels'],'images':len(manifest['images']),
            'thresholds':result,'threshold_selection':'No automatic runtime change; review held-out per-class misses and false positives',
            'not_covered':manifest.get('not_covered',[])}


def run(args):
    path=Path(args.manifest)
    manifest=json.loads(path.read_text()); validate_manifest(manifest)
    model=OnnxDetector(args.model,confidence=min(args.thresholds))
    unsupported=set(manifest['labels'])-set(model.names.values())
    if unsupported: raise ValueError(f'Labels absent from this model: {sorted(unsupported)}; record as not_covered instead')
    predictions={}; hashes={}
    for sample in manifest['images']:
        data=(path.parent/sample['file']).read_bytes()
        digest=hashlib.sha256(data).hexdigest()
        if digest in hashes and hashes[digest]!=sample['split']:
            raise ValueError('Same image bytes appear in tuning and validation')
        hashes[digest]=sample['split']
        predictions[sample['id']]=[{'label':d.label,'score':d.score,'box':list(d.box)} for d in model(data)]
    report=evaluate(manifest,predictions,args.thresholds,args.iou)
    report['model_sha256']=hashlib.sha256(Path(args.model).read_bytes()).hexdigest()
    report['status']='EVALUATED; no navigation-safety certification'
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',required=True); p.add_argument('--model',default='models/yolov8n.onnx')
    p.add_argument('--thresholds',nargs='+',type=float,default=[.25,.35,.45,.55])
    p.add_argument('--iou',type=float,default=.5); p.add_argument('--output',default='qa/quality/evaluation.json')
    args=p.parse_args()
    if not args.thresholds or any(not 0<=t<=1 for t in args.thresholds): p.error('Confidence thresholds must be 0..1')
    run(args)
