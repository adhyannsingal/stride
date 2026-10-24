"""Opt-in real detector contract test; never substitutes a test detector."""

import os
from pathlib import Path

import pytest

from stride_backend.detector import load_detector
from tests.live_helpers import running


@pytest.mark.skipif(
    not os.getenv("STRIDE_INTEGRATION_DETECTOR_FACTORY") or not os.getenv("STRIDE_INTEGRATION_JPEG"),
    reason="Set STRIDE_INTEGRATION_DETECTOR_FACTORY and STRIDE_INTEGRATION_JPEG to test the real adapter",
)
def test_real_detector_through_continuous_worker():
    detector = load_detector(os.environ["STRIDE_INTEGRATION_DETECTOR_FACTORY"])
    jpeg = Path(os.environ["STRIDE_INTEGRATION_JPEG"]).read_bytes()
    with running(jpeg, detector=detector) as live:
        assert live.action("start").status_code == 200
        assert live.upload().status_code == 202
        result = live.wait(lambda state: state.status == "live")
        assert result["frame_id"] == "frame-1"
        assert result["age_ms"] <= 1000
        assert result["published_results"] == 1
