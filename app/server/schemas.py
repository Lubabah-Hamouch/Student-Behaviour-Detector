"""Response models for the API."""
from pydantic import BaseModel, ConfigDict, Field


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


class ImageDetectionResponse(BaseModel):
    width: int
    height: int
    inference_ms: float
    detections: list[DetectionOut]
    counts: dict[str, int]


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
    classes: list[ClassInfo]
    metrics: ModelMetrics | None  # None if results/metrics_summary.json is missing or unreadable
