"""Focal server entry point.

Run from the project root:
    uvicorn app.server.main:app --port 8000
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import config
from .inference import Detector
from .routes import image, meta

log = logging.getLogger("focal")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.detector = None
    app.state.load_error = None
    try:
        app.state.detector = Detector(config.MODEL_PATH, config.IMGSZ, config.CONF_MIN, config.IOU, config.DEVICE)
        log.info("Model loaded: %s on %s", config.MODEL_PATH, app.state.detector.device_label)
    except Exception as exc:  # keep the server up so /api/health can report why the model is missing
        app.state.load_error = str(exc)
        log.exception("Could not load the model")
    yield


app = FastAPI(title="Focal", lifespan=lifespan)
app.include_router(meta.router)
app.include_router(image.router)
