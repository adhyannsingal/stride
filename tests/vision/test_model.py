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


def test_candidate_filter_threshold_empty_nonfinite_and_invalid_geometry():
    d=OnnxDetector.__new__(OnnxDetector)
    d.names,d.confidence,d.nms_iou={0:'chair',1:'person'},.5,.45
    rows=np.array([
        [50,50,20,20,.5,.1],       # Threshold included.
        [150,50,20,20,.499,.1],     # Below threshold excluded.
        [50,150,20,20,1.01,.9],     # Invalid winning score cannot fall back to another class.
        [150,150,-20,20,.9,.1],     # Inverted geometry excluded.
        [float('inf'),50,20,20,.9,.1],
        [250,250,20,20,.1,.8],
    ],dtype=np.float32)
    found=d.decode(rows.T[None],(1,0,0,320,320))
    assert [item.label for item in found]==['person','chair']
    assert d.decode(np.zeros((1,6,2100),dtype=np.float32),(1,0,0,320,320))==[]
    assert d.decode(np.full((1,6,4),np.nan),(1,0,0,320,320))==[]


def test_diagnostic_capture_preserves_aspect_ratio_and_reports_dark_input():
    from app.vision.capture import encode_capture
    jpeg,dimensions,quality=encode_capture(np.zeros((1080,1920,3),dtype=np.uint8))
    assert dimensions==(640,360)
    assert read_jpeg(jpeg).size==dimensions
    assert quality['nearly_black']
    # Portrait frames retain orientation and aspect instead of stretching to 4:3.
    _,dimensions,_=encode_capture(np.full((800,400,3),128,dtype=np.uint8))
    assert dimensions==(240,480)
