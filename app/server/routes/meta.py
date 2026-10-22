"""Health and model-information endpoints."""
import json

from fastapi import APIRouter, Depends

from .. import config
from ..deps import get_detector
from ..inference import Detector
from ..schemas import ClassInfo, HealthResponse, ModelInfoResponse, ModelMetrics, ModelSummary

router = APIRouter(prefix="/api")


def _architecture(weights_name: str | None) -> str:
    """'yolov8m.pt' -> 'YOLOv8m'."""
    stem = (weights_name or "").rsplit(".", 1)[0]
    return f"YOLO{stem[4:]}" if stem.lower().startswith("yolo") else (stem or "unknown")


def _read_metrics() -> tuple[ModelMetrics | None, str | None]:
    """Parsed results/metrics_summary.json and the pretrained weights name it records, or (None, None)."""
    try:
        raw = json.loads(config.METRICS_PATH.read_text(encoding="utf-8"))
        metrics = ModelMetrics.model_validate(raw)
        return metrics, raw.get("model")
    except (OSError, ValueError):
        return None, None


def _summary(detector: Detector, pretrained_name: str | None) -> ModelSummary:
    return ModelSummary(
        architecture=_architecture(pretrained_name),
        weights=_display_path(detector.weights),
        imgsz=detector.imgsz,
        conf_min=detector.conf,
        iou=detector.iou,
    )


def _display_path(path) -> str:
    try:
        return path.relative_to(config.PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name


@router.get("/health", response_model=HealthResponse)
def health(detector: Detector = Depends(get_detector)):
    _, pretrained = _read_metrics()
    return HealthResponse(
        status="ok",
        device=detector.device_label,
        model=_summary(detector, pretrained),
        classes=[detector.names[i] for i in sorted(detector.names)],
    )


@router.get("/model", response_model=ModelInfoResponse)
def model_info(detector: Detector = Depends(get_detector)):
    metrics, pretrained = _read_metrics()
    classes = [
        ClassInfo(
            id=i,
            name=detector.names[i],
            definition=config.CLASS_DEFINITIONS.get(detector.names[i], ""),
            experimental=detector.names[i] in config.EXPERIMENTAL_CLASSES,
        )
        for i in sorted(detector.names)
    ]
    return ModelInfoResponse(model=_summary(detector, pretrained), default_confidence=config.DEFAULT_CONF,
                             source_url=config.SOURCE_URL, classes=classes, metrics=metrics)
