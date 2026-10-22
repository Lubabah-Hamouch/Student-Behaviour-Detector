"""Model wrapper: loads the YOLO weights once and turns an image into normalised detections."""
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO


@dataclass(frozen=True)
class Detection:
    class_id: int
    name: str
    confidence: float
    x1: float  # box corners, normalised to [0, 1] of the image width / height
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class DetectionResult:
    width: int
    height: int
    inference_ms: float  # model time for this image: preprocessing, forward pass and NMS
    detections: list[Detection]


class Detector:
    def __init__(self, weights: Path, imgsz: int, conf: float, iou: float, device: str | None = None):
        if not weights.exists():
            raise FileNotFoundError(f"Model weights not found: {weights}")
        self.weights = weights
        self.imgsz, self.conf, self.iou = imgsz, conf, iou
        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self.half = self.device.startswith("cuda")
        self.model = YOLO(str(weights))
        self.names: dict[int, str] = dict(self.model.names)
        self._lock = threading.Lock()  # one model instance: serialise access to it
        self.predict(np.zeros((imgsz, imgsz, 3), dtype=np.uint8))  # warm-up (CUDA init, cuDNN autotune)

    @property
    def device_label(self) -> str:
        if self.device.startswith("cuda"):
            return f"{self.device} ({torch.cuda.get_device_name(self.device)})"
        return self.device

    def predict(self, image_bgr: np.ndarray) -> DetectionResult:
        height, width = image_bgr.shape[:2]
        with self._lock:
            started = time.perf_counter()
            result = self.model.predict(image_bgr, imgsz=self.imgsz, conf=self.conf, iou=self.iou,
                                        device=self.device, half=self.half, verbose=False)[0]
            elapsed_ms = (time.perf_counter() - started) * 1000

        boxes = result.boxes
        corners = boxes.xyxyn.cpu().numpy().clip(0.0, 1.0)
        confidences = boxes.conf.cpu().numpy()
        class_ids = boxes.cls.cpu().numpy().astype(int)
        detections = [
            Detection(int(c), self.names[int(c)], round(float(p), 4), *(round(float(v), 4) for v in box))
            for box, p, c in zip(corners, confidences, class_ids)
        ]
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return DetectionResult(width, height, round(elapsed_ms, 1), detections)
