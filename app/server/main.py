"""Focal server entry point.

Run from the project root:
    uvicorn app.server.main:app --port 8000
"""
import logging
import mimetypes
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config
from .inference import Detector
from .routes import image, live, meta, pages, video
from .video_jobs import JobManager

log = logging.getLogger("focal")
mimetypes.add_type("font/woff2", ".woff2")  # not in every platform's registry; static serving relies on it


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.detector = None
    app.state.jobs = None
    app.state.load_error = None
    app.state.live_sessions = 0
    try:
        app.state.detector = Detector(config.MODEL_PATH, config.IMGSZ, config.CONF_MIN, config.IOU, config.DEVICE,
                                      config.WARMUP_SHAPES, config.WARMUP_BATCH)
        app.state.jobs = JobManager(app.state.detector, config.UPLOAD_DIR)
        app.state.jobs.start()
        log.info("Model loaded: %s on %s", config.MODEL_PATH, app.state.detector.device_label)
    except Exception as exc:  # keep the server up so /api/health can report why the model is missing
        app.state.load_error = str(exc)
        log.exception("Could not load the model")
    yield
    if app.state.jobs is not None:
        app.state.jobs.stop()
    if app.state.detector is not None:
        app.state.detector.close()


def create_app() -> FastAPI:
    """Build an app with its own state (tests use this to get an app that is independent of the global one)."""
    application = FastAPI(title="Focal", lifespan=lifespan)
    application.include_router(meta.router)
    application.include_router(image.router)
    application.include_router(video.router)
    application.include_router(live.router)
    application.include_router(pages.router)
    application.mount("/static", StaticFiles(directory=config.WEB_DIR), name="static")
    return application


app = create_app()
