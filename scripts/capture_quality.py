"""Collect a small private webcam review set. Never auto-labels ground truth."""
import argparse
import json
from pathlib import Path
import time
from uuid import uuid4
import cv2
from app.vision.capture import encode_capture


def private_output(path):
    target=Path(path).resolve()
    root=Path('qa/private').resolve()
    if not target.is_relative_to(root): raise ValueError('Review images must stay under ignored qa/private/')
    if target.exists() and any(target.iterdir()): raise ValueError('Review folder is not empty; choose a new folder')
    return target


def capture(args):
    output=private_output(args.output); output.mkdir(parents=True,exist_ok=True)
    manifest={'scope':'private webcam review set; NOT accuracy ground truth until human-reviewed',
              'labels':['person','chair','cup','bottle'],
              'not_covered':['stairs','drop-offs','glass','walls','safe free space','measured object distance'],
              'images':[]}
    cap=cv2.VideoCapture(args.camera); skipped=0
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
        if not cap.isOpened(): raise RuntimeError('Webcam unavailable; no replacement images')
        for attempt in range(args.frames*3):
            captured=time.time_ns()//1_000_000
            ok,image=cap.read()
            if not ok: raise RuntimeError('Webcam read failed')
            jpeg,dimensions,quality=encode_capture(image)
            if quality['nearly_black']:
                skipped+=1
            else:
                number=len(manifest['images'])+1
                filename=f'frame-{number:03d}.jpg'
                (output/filename).write_bytes(jpeg)
                manifest['images'].append({'id':str(uuid4()),'scene_id':args.scene_id,'split':args.split,
                    'file':filename,'reviewed':False,'complete_for_labels':False,'objects':[],
                    'conditions':[],'captured_ms':captured,'source':'real','capture_adapter':'opencv_webcam',
                    'width':dimensions[0],'height':dimensions[1]})
                (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
            if len(manifest['images'])>=args.frames: break
            time.sleep(args.interval)
    finally:
        cap.release()
    count=len(manifest['images'])
    result={'captured':count,'dark_frames_skipped':skipped,'manifest':str(output/'manifest.json'),
            'reviewed':False,'accuracy':'NOT RUN','status':'CAPTURED' if count==args.frames else 'INCOMPLETE'}
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True); p.add_argument('--scene-id',required=True)
    p.add_argument('--split',choices=['tuning','validation'],default='tuning')
    p.add_argument('--frames',type=int,default=12); p.add_argument('--interval',type=float,default=2)
    p.add_argument('--camera',type=int,default=0)
    args=p.parse_args()
    if not 1<=args.frames<=50 or args.interval<.2: p.error('Use 1..50 frames and interval >=.2 seconds')
    capture(args)
