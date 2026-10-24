from types import SimpleNamespace
import json
import numpy as np
import pytest
from scripts.capture_quality import private_output,capture


def test_quality_images_cannot_be_written_outside_private_folder(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError): private_output(tmp_path/'public')
    target=tmp_path/'qa/private/review'; target.mkdir(parents=True)
    (target/'existing.jpg').write_bytes(b'existing')
    with pytest.raises(ValueError): private_output(target)


def test_capture_produces_unreviewed_annotations_and_releases_camera(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    class Camera:
        released=False
        def set(self,*args): pass
        def isOpened(self): return True
        def read(self): return True,np.full((48,64,3),128,dtype=np.uint8)
        def release(self): self.released=True
    camera=Camera()
    monkeypatch.setattr('scripts.capture_quality.cv2.VideoCapture',lambda _:camera)
    monkeypatch.setattr('scripts.capture_quality.time.sleep',lambda _:None)
    args=SimpleNamespace(output='qa/private/review',camera=0,frames=2,interval=.2,
                         scene_id='test-fixture-scene',split='tuning')
    result=capture(args)
    assert result['captured']==2 and result['accuracy']=='NOT RUN' and camera.released
    manifest=json.loads((tmp_path/'qa/private/review/manifest.json').read_text())
    assert all(not sample['reviewed'] and not sample['complete_for_labels'] and not sample['objects']
               for sample in manifest['images'])


def test_camera_failure_releases_device(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    class Camera:
        released=False
        def set(self,*args): pass
        def isOpened(self): return False
        def release(self): self.released=True
    camera=Camera()
    monkeypatch.setattr('scripts.capture_quality.cv2.VideoCapture',lambda _:camera)
    with pytest.raises(RuntimeError):
        capture(SimpleNamespace(output='qa/private/review',camera=0))
    assert camera.released
