import io
import numpy as np
import pytest
from PIL import Image
from app.vision.model import OnnxDetector, preprocess, read_jpeg


def test_decoder_letterbox_nms_and_class_separation():
    d = OnnxDetector.__new__(OnnxDetector)
    d.names, d.confidence, d.nms_iou = {0:'chair',1:'person'}, .35, .45
    # Original 640x480 letterboxed to 320 square: 40 px vertical padding.
    rows = np.array([[160,160,160,120,.9,.1], [160,160,160,120,.8,.1],
                     [160,160,160,120,.1,.8], [160,160,160,120,float('nan'),.1]])
    out = d.decode(rows.T[None], (.5,0,40,640,480))
    assert len(out) == 2
    assert out[0].box == (.25,.25,.75,.75)
    with pytest.raises(ValueError):
        d.decode(np.zeros((1,300,6)), (.5,0,40,640,480))


def test_jpeg_limits_and_rgb_preprocessing():
    with pytest.raises(Exception):
        read_jpeg(b'not jpeg')
    out = io.BytesIO()
    Image.new('RGB',(640,480),(255,0,0)).save(out,format='JPEG')
    tensor, geo = preprocess(read_jpeg(out.getvalue()),320)
    assert tensor.shape == (1,3,320,320) and tensor.dtype == np.float32
    assert geo == (.5,0,40,640,480)
    assert tensor[0,0,100,100] > .9 and tensor[0,2,100,100] < .1
