"""Test frames. The dataset frames show real students and are not part of the public repository, so tests that merely
need *an* image use a synthetic one, and tests that need real classroom content are skipped when the frame is missing.

Set FOCAL_TEST_FRAME to point at a different real frame (or at a missing file to see how a clone without the data behaves).
"""
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.server import config

REAL_FRAME = Path(os.environ.get("FOCAL_TEST_FRAME", config.PROJECT_ROOT / "data" / "dataset" / "images" / "image147.jpg"))
HAS_REAL_FRAME = REAL_FRAME.exists()

requires_real_frame = pytest.mark.skipif(
    not HAS_REAL_FRAME,
    reason="needs a real classroom frame; the dataset frames are not included in the public repository",
)


def sample_frame() -> np.ndarray:
    """A real classroom frame when the dataset is present, otherwise a synthetic 832x464 BGR frame (no detections expected)."""
    if HAS_REAL_FRAME:
        return cv2.imread(str(REAL_FRAME))
    rng = np.random.default_rng(0)
    gradient = np.tile(np.linspace(40, 200, 832, dtype=np.uint8), (464, 1))
    frame = np.stack([gradient, gradient[::-1], gradient // 2], axis=2)
    return np.clip(frame.astype(np.int16) + rng.integers(-12, 12, frame.shape), 0, 255).astype(np.uint8)


def sample_jpeg() -> bytes:
    ok, buf = cv2.imencode(".jpg", sample_frame(), [cv2.IMWRITE_JPEG_QUALITY, 90])
    assert ok
    return buf.tobytes()
