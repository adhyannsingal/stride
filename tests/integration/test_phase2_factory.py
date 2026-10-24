"""Factory checksum failure must not produce a pretend configured detector."""
import pytest
pytest.importorskip('stride_backend',reason='Add backend_phase2 to PYTHONPATH')
from app.vision.phase2 import build_detector
from stride_backend.main import create_app
from stride_backend.settings import Settings


def test_invalid_artifact_fails_closed_without_replacing_provider(tmp_path,monkeypatch):
    path=tmp_path/'model.onnx'; path.write_bytes(b'not a model')
    monkeypatch.setenv('LIVE_DETECTOR_MODEL_PATH',str(path))
    monkeypatch.setenv('LIVE_DETECTOR_MODEL_SHA256','0'*64)
    with pytest.raises(ValueError,match='checksum mismatch'): build_detector()
    app=create_app(Settings(_env_file=None,local_dev=True,detector_factory='app.vision.phase2:build_detector'))
    assert app.state.inference_worker.detector is None
    assert app.state.frame_store.detector_error=='detector_load_error'
