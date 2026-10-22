"""Response models for the API."""
from pydantic import BaseModel, ConfigDict, Field

from .inference import Detection


class Box(BaseModel):
    """Corners normalised to [0, 1] of the image width / height."""
    x1: float
    y1: float
    x2: float
    y2: float


class DetectionOut(BaseModel):
    class_id: int
    name: str
    confidence: float
    box: Box


def detection_out(d: Detection) -> DetectionOut:
    return DetectionOut(class_id=d.class_id, name=d.name, confidence=d.confidence,
                        box=Box(x1=d.x1, y1=d.y1, x2=d.x2, y2=d.y2))


class ImageDetectionResponse(BaseModel):
    width: int
    height: int
    inference_ms: float
    detections: list[DetectionOut]
    counts: dict[str, int]


class VideoJobCreated(BaseModel):
    job_id: str
    status: str
    width: int
    height: int
    duration: float | None  # seconds; None if the container does not report a frame count
    native_fps: float
    sample_fps: float  # frames analysed per second of video
    frames_total: int  # estimate; 0 if unknown


class JobStatus(BaseModel):
    job_id: str
    status: str  # queued | running | done | failed
    progress: float  # 0 to 1
    frames_done: int
    frames_total: int
    error: str | None = None


class VideoFrame(BaseModel):
    t: float  # seconds from the start of the video
    detections: list[DetectionOut]


class VideoSummary(BaseModel):
    frames_processed: int
    detections_total: int
    inference_ms_mean: float
    processing_seconds: float


class VideoResult(BaseModel):
    job_id: str
    width: int
    height: int
    duration: float
    native_fps: float
    sample_fps: float
    frames: list[VideoFrame]
    summary: VideoSummary


class ClassInfo(BaseModel):
    id: int
    name: str
    definition: str
    experimental: bool


class ModelSummary(BaseModel):
    architecture: str
    weights: str
    imgsz: int
    conf_min: float
    iou: float


class HealthResponse(BaseModel):
    status: str
    device: str
    model: ModelSummary
    classes: list[str]


class ClassMetrics(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    precision: float
    recall: float
    map50: float = Field(alias="mAP50")
    map50_95: float = Field(alias="mAP50-95")
    instances: int | None = None


class SplitMetrics(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    map50: float = Field(alias="mAP50")
    map50_95: float = Field(alias="mAP50-95")
    precision: float
    recall: float
    per_class: dict[str, ClassMetrics]


class ModelMetrics(BaseModel):
    run: str
    epochs_completed: int
    val: SplitMetrics
    test: SplitMetrics


class ModelInfoResponse(BaseModel):
    model: ModelSummary
    default_confidence: float  # initial value for the UI's confidence slider
    source_url: str | None  # repository link, if configured
    classes: list[ClassInfo]
    metrics: ModelMetrics | None  # None if results/metrics_summary.json is missing or unreadable
