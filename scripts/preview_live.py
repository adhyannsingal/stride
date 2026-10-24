"""Live local webcam diagnostic with real YOLO boxes; no server/UI replacement.
Q/Esc quit, P pause/resume, +/- adjust diagnostic confidence only. No video saved.
"""
import argparse
from collections import deque
import time
import cv2
import numpy as np
from app.vision.capture import encode_capture
from app.vision.model import OnnxDetector


TITLE='Stride — LIVE webcam detection (local diagnostic)'


def preview(args):
    detector=OnnxDetector(args.model,confidence=args.confidence)
    cap=None; paused=False; ticks=deque(maxlen=60); started=time.monotonic(); seen=False; read_failures=0
    cv2.namedWindow(TITLE,cv2.WINDOW_NORMAL)
    cv2.resizeWindow(TITLE,1000,650)
    print('Live window opening. Focus it: Q/Esc quit, P pause/resume, +/- confidence. No frames saved.',flush=True)
    try:
        while not args.seconds or time.monotonic()-started<args.seconds:
            began=time.monotonic()
            if paused:
                image=np.zeros((480,720,3),dtype=np.uint8)
                cv2.putText(image,'PAUSED — press P to resume',(20,90),cv2.FONT_HERSHEY_SIMPLEX,.8,(255,255,255),2)
            else:
                if cap is None:
                    cap=cv2.VideoCapture(args.camera)
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH,640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
                    if not cap.isOpened(): raise RuntimeError('Webcam unavailable; check camera permission and close competing capture apps')
                ok,raw=cap.read()
                if not ok:
                    read_failures+=1
                    waiting=np.zeros((360,640,3),dtype=np.uint8)
                    cv2.putText(waiting,'Waiting for webcam... close other camera apps',(15,100),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),1)
                    cv2.imshow(TITLE,waiting)
                    if cv2.waitKey(50)&0xff in (27,ord('q'),ord('Q')): break
                    if read_failures>=30: raise RuntimeError('Webcam unavailable after retries; close competing capture apps')
                    if read_failures%10==0: cap.release(); cap=None
                    continue
                read_failures=0
                jpeg,_,quality=encode_capture(raw)
                found=detector(jpeg)
                elapsed=(time.monotonic()-began)*1000
                image=cv2.imdecode(np.frombuffer(jpeg,dtype=np.uint8),cv2.IMREAD_COLOR)
                h,w=image.shape[:2]
                if elapsed>=1000:
                    found=[]
                for obj in found:
                    x1,y1,x2,y2=(int(v*d) for v,d in zip(obj.box,(w,h,w,h)))
                    x1,y1=max(0,min(w-1,x1)),max(0,min(h-1,y1))
                    x2,y2=max(0,min(w-1,x2)),max(0,min(h-1,y2))
                    center=(obj.box[0]+obj.box[2])/2
                    position='left' if center<1/3 else 'right' if center>2/3 else 'center'
                    cv2.rectangle(image,(x1,y1),(x2,y2),(0,220,255),2)
                    text=f'{obj.label} {obj.score:.2f} | {position}'
                    cv2.putText(image,text,(x1,max(45,y1-7)),cv2.FONT_HERSHEY_SIMPLEX,.48,(0,0,0),3,cv2.LINE_AA)
                    cv2.putText(image,text,(x1,max(45,y1-7)),cv2.FONT_HERSHEY_SIMPLEX,.48,(0,220,255),1,cv2.LINE_AA)
                now=time.monotonic(); ticks.append(now)
                fps=(len(ticks)-1)/(ticks[-1]-ticks[0]) if len(ticks)>1 else 0
                header=f'LIVE LOCAL | {fps:.1f} fps | read/result {elapsed:.0f} ms | score >= {detector.confidence:.2f}'
                if quality['nearly_black']: header='CAMERA INPUT NEARLY BLACK — uncover lens / check lighting'
                if elapsed>=1000: header='STALE RESULT SUPPRESSED — no current boxes'
                cv2.rectangle(image,(0,0),(w,30),(20,20,20),-1)
                cv2.putText(image,header,(8,21),cv2.FONT_HERSHEY_SIMPLEX,.44,(255,255,255),1,cv2.LINE_AA)
                cv2.rectangle(image,(0,h-25),(w,h),(20,20,20),-1)
                cv2.putText(image,'Q quit | P pause | +/- score | Image position, NOT distance or a safe turn',
                            (8,h-8),cv2.FONT_HERSHEY_SIMPLEX,.38,(255,255,255),1,cv2.LINE_AA)
                if not seen:
                    print(f'LIVE: {w}x{h}, real detector running, first labels: {[d.label for d in found]}',flush=True)
                    seen=True
            cv2.imshow(TITLE,image)
            key=cv2.waitKey(1)&0xff
            if key in (27,ord('q'),ord('Q')): break
            if key in (ord('p'),ord('P')):
                paused=not paused; ticks.clear()
                if cap is not None: cap.release(); cap=None
            if key in (ord('+'),ord('=')): detector.confidence=min(.9,round(detector.confidence+.05,2))
            if key==ord('-'): detector.confidence=max(.1,round(detector.confidence-.05,2))
            if cv2.getWindowProperty(TITLE,cv2.WND_PROP_VISIBLE)<1: break
            time.sleep(max(0,1/args.hz-(time.monotonic()-began)))
    finally:
        if cap is not None: cap.release()
        cv2.destroyAllWindows()
        print('Preview stopped; webcam released.',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',default='models/yolov8n.onnx'); p.add_argument('--camera',type=int,default=0)
    p.add_argument('--confidence',type=float,default=.35); p.add_argument('--hz',type=float,default=10)
    p.add_argument('--seconds',type=float,default=0,help='0 leaves preview open until Q/Esc')
    args=p.parse_args()
    if not 0<args.confidence<1 or args.hz<=0 or args.seconds<0: p.error('Invalid confidence/rate/duration')
    preview(args)
