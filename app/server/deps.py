"""Shared FastAPI dependencies."""
from fastapi import HTTPException, Request

from .inference import Detector


def get_detector(request: Request) -> Detector:
    detector = getattr(request.app.state, "detector", None)
    if detector is None:
        reason = getattr(request.app.state, "load_error", None) or "model not loaded"
        raise HTTPException(status_code=503, detail=f"Model unavailable: {reason}")
    return detector
