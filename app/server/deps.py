"""Shared FastAPI dependencies."""
from fastapi import HTTPException, Request

from .inference import Detector
from .video_jobs import JobManager


def _unavailable(request: Request) -> HTTPException:
    reason = getattr(request.app.state, "load_error", None) or "model not loaded"
    return HTTPException(status_code=503, detail=f"Model unavailable: {reason}")


def get_detector(request: Request) -> Detector:
    detector = getattr(request.app.state, "detector", None)
    if detector is None:
        raise _unavailable(request)
    return detector


def get_jobs(request: Request) -> JobManager:
    jobs = getattr(request.app.state, "jobs", None)
    if jobs is None:
        raise _unavailable(request)
    return jobs
