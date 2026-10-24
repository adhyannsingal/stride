"""Diagnostic webcam encoding; browser capture remains Agent 2's responsibility."""
import cv2
import numpy as np


def encode_capture(image, max_width=640, max_height=480):
    if image.ndim!=3 or image.shape[2]!=3 or image.dtype!=np.uint8:
        raise ValueError('Expected uint8 BGR camera frame')
    height,width=image.shape[:2]
    if not height or not width or min(max_width,max_height)<=0:
        raise ValueError('Invalid capture dimensions')
    scale=min(max_width/width,max_height/height,1.)
    target=(max(1,round(width*scale)),max(1,round(height*scale)))
    if target!=(width,height):
        image=cv2.resize(image,target,interpolation=cv2.INTER_AREA)
    mean,std=float(image.mean()),float(image.std())
    ok,jpeg=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,95])
    if not ok:
        raise RuntimeError('JPEG encode failed')
    return jpeg.tobytes(),target,{'mean_pixel':mean,'std_pixel':std,'nearly_black':mean<2 and std<2}
