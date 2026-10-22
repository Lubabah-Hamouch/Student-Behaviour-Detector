"""Paths, limits and class metadata for the Focal server.

Paths and inference settings can be overridden with FOCAL_* environment variables.
"""
import os
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

# Upload limits. They are enforced once the upload has been received, so a reverse proxy
# should also cap request size when the app is deployed.
MAX_IMAGE_MB = 25
MAX_IMAGE_PIXELS = 50_000_000

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
