from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from stride_backend.main import create_app
from stride_backend.settings import Settings


@pytest.fixture
def settings():
    return Settings(_env_file=None, device_token="test-device-token", local_dev=False)


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def jpeg():
    output = BytesIO()
    with Image.new("RGB", (32, 24), color="navy") as image:
        image.save(output, format="JPEG")
    return output.getvalue()


@pytest.fixture
def metadata():
    return {
        "session_id": "session-1", "device_id": "camera-1", "boot_id": "boot-1",
        "frame_id": "frame-1", "sequence": "1", "captured_ms": "42", "source": "fixture",
    }


@pytest.fixture
def upload(client, jpeg, metadata):
    def send(*, data=None, image=None, headers=None, content_type="image/jpeg"):
        return client.post(
            "/frame", data=metadata if data is None else data,
            files={"file": ("frame.jpg", jpeg if image is None else image, content_type)},
            headers={"X-Device-Token": "test-device-token"} if headers is None else headers,
        )
    return send
