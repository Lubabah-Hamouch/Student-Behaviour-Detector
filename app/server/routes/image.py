"""Single-image detection endpoint."""
import io
from collections import Counter

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from .. import config
from ..deps import get_detector
from ..inference import Detector
from ..schemas import ImageDetectionResponse, detection_out

router = APIRouter(prefix="/api/detect")


def _decode(data: bytes) -> np.ndarray:
    """Bytes -> BGR image (EXIF orientation applied), rejecting corrupt or oversized images."""
    try:
        with Image.open(io.BytesIO(data)) as probe:  # reads only the header
            width, height = probe.size
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="The file is not a readable image.")
    if width * height > config.MAX_IMAGE_PIXELS:
        raise HTTPException(status_code=413,
                            detail=f"Image is too large ({width}x{height}); the limit is "
                                   f"{config.MAX_IMAGE_PIXELS // 1_000_000} megapixels.")
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="The file is not a readable image.")
    return image


@router.post("/image", response_model=ImageDetectionResponse)
async def detect_image(file: UploadFile = File(...), detector: Detector = Depends(get_detector)):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="Upload an image file (JPEG, PNG, WebP or BMP).")
    limit = config.MAX_IMAGE_MB * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"Image is larger than {config.MAX_IMAGE_MB} MB.")
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    image = await run_in_threadpool(_decode, data)
    result = await run_in_threadpool(detector.predict, image)

    return ImageDetectionResponse(
        width=result.width,
        height=result.height,
        inference_ms=result.inference_ms,
        detections=[detection_out(d) for d in result.detections],
        counts=dict(Counter(d.name for d in result.detections)),
    )
