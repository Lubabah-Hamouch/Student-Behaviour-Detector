"""Paths, limits and class metadata for the Focal server.

Paths and inference settings can be overridden with FOCAL_* environment variables.
"""
import os
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_PATH = Path(os.environ.get("FOCAL_MODEL", PROJECT_ROOT / "models" / "best.pt"))
METRICS_PATH = Path(os.environ.get("FOCAL_METRICS", PROJECT_ROOT / "results" / "metrics_summary.json"))
LIMITATIONS_PATH = PROJECT_ROOT / "docs" / "LIMITATIONS.md"

# Inference. The IoU matches the value the reported metrics were computed with (Ultralytics' default of 0.7).
IMGSZ = int(os.environ.get("FOCAL_IMGSZ", 640))
CONF_MIN = float(os.environ.get("FOCAL_CONF_MIN", 0.10))  # lowest confidence returned; clients filter above it
IOU = float(os.environ.get("FOCAL_IOU", 0.7))
DEVICE = os.environ.get("FOCAL_DEVICE") or None  # None = CUDA if available, else CPU

# Warm-up input shapes (height, width) run at startup so the first real request is not slow: 16:9 video frames
# (832x464, 1280x720 and 1920x1080 all letterbox to the same 640x384 model input) and 4:3 webcam frames.
WARMUP_SHAPES = ((464, 832), (480, 640))
WARMUP_BATCH = 4  # also warm up a batch of this size (used for video)

# Upload limits. They are enforced once the upload has been received, so a reverse proxy
# should also cap request size when the app is deployed.
MAX_IMAGE_MB = 25
MAX_IMAGE_PIXELS = 50_000_000

# Video jobs.
UPLOAD_DIR = Path(tempfile.gettempdir()) / "focal_uploads"  # wiped when the server starts
MAX_VIDEO_MB = 200
MAX_VIDEO_SECONDS = 180
DEFAULT_SAMPLE_FPS = 10.0  # frames analysed per second of video
MAX_SAMPLE_FPS = 30.0
VIDEO_BATCH = 4  # frames per forward pass; small, so live frames are not kept waiting long
MAX_PENDING_JOBS = 4
JOB_TTL_SECONDS = 3600  # finished jobs (and their results) are kept in memory this long
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}

# Live camera over WebSocket.
MAX_LIVE_SESSIONS = 2
MAX_LIVE_FRAME_KB = 2048

# Shown in the model-info section. hand_raised and phone follow the original annotation guide.
CLASS_DEFINITIONS = {
    "distracted": "Looking away or sideways, not oriented toward the lesson.",
    "concentrating": "Attentive, forward-facing focus.",
    "hand_raised": "Hand clearly raised above shoulder level to get the teacher's attention.",
    "phone": "Actively using or looking at a phone, held in the hands or near the face.",
    "sleeping": "Eyes closed, whether head-down or upright.",
}
# Classes the UI marks as experimental (see docs/LIMITATIONS.md).
EXPERIMENTAL_CLASSES = {"sleeping"}
