import io
from email.message import Message
from PIL import Image
import pytest
from app.vision.http_camera import HttpCamera


class Response:
    def __init__(self, content_type='image/jpeg', age='10000'):
        self.headers=Message(); self.headers['Content-Type']=content_type
        if age is not None: self.headers['X-Stride-Frame-Age-Us']=age
        data=io.BytesIO(); Image.new('RGB',(32,24),'red').save(data,format='JPEG')
        self.data=data.getvalue()
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,n): return self.data[:n]


class Opener:
    def __init__(self,response): self.response=response
    def open(self,request,timeout): return self.response


@pytest.mark.parametrize('url',['https://192.168.1.2/capture','http://8.8.8.8/capture','http://camera.example/capture','http://u:p@192.168.1.2/capture','http://0.0.0.0/capture'])
def test_rejects_nonlocal_or_credential_urls(url):
    with pytest.raises(ValueError): HttpCamera(url)


def test_decodes_real_jpeg_and_exposes_device_age_bound():
    camera=HttpCamera('http://192.168.1.2/capture',Opener(Response()))
    ok,image=camera.read()
    assert ok and image.shape==(24,32,3) and camera.captured_at is not None
    assert image[0,0,2]>200  # RGB -> OpenCV BGR conversion.
    camera.release()
    assert camera.read()==(False,None)


@pytest.mark.parametrize('age',['-1','1000000','not-an-age'])
def test_rejects_stale_or_invalid_reported_age(age):
    camera=HttpCamera('http://192.168.1.2/capture',Opener(Response(age=age)))
    assert camera.read()==(False,None)


def test_missing_age_is_visual_only_and_html_is_rejected():
    camera=HttpCamera('http://192.168.1.2/capture',Opener(Response(age=None)))
    assert camera.read()[0] and camera.captured_at is None
    camera=HttpCamera('http://192.168.1.2/capture',Opener(Response(content_type='text/html')))
    assert camera.read()==(False,None)
