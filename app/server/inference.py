"""Model wrapper: loads the YOLO weights once and turns images into normalised detections."""
import time
from concurrent.futures import ThreadPoolExecutor
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
    def __init__(self, weights: Path, imgsz: int, conf: float, iou: float, device: str | None = None,
                 warmup_shapes: tuple = (), warmup_batch: int = 1):
        if not weights.exists():
            raise FileNotFoundError(f"Model weights not found: {weights}")
        self.weights = weights
        self.imgsz, self.conf, self.iou = imgsz, conf, iou
        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self.half = self.device.startswith("cuda")
        self.model = YOLO(str(weights))
        self.names: dict[int, str] = dict(self.model.names)
        # All inference runs on this one thread, warm-up included: CUDA/cuDNN keep per-thread state, so a request
        # served on a thread that never ran the model pays a start-up cost, and one thread also serialises GPU access.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")
        self._warm_up(warmup_shapes or [(imgsz, imgsz)], warmup_batch)

    def close(self) -> None:
        self._executor.shutdown(wait=False)

    @property
    def device_label(self) -> str:
        if self.device.startswith("cuda"):
            return f"{self.device} ({torch.cuda.get_device_name(self.device)})"
        return self.device

    def _warm_up(self, shapes, batch: int) -> None:
        """Run the model once per input shape (and once as a batch) so CUDA and cuDNN initialise before the first
        real request. Noise frames at a very low confidence make sure the NMS path runs too."""
        rng = np.random.default_rng(0)
        for height, width in shapes:
            frame = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
            self.predict_batch([frame], conf=0.001)
            if batch > 1:
                self.predict_batch([frame] * batch, conf=0.001)

    def predict(self, image_bgr: np.ndarray) -> DetectionResult:
        return self.predict_batch([image_bgr])[0]

    def predict_batch(self, images: list[np.ndarray], conf: float | None = None) -> list[DetectionResult]:
        """Detect on several same-shaped BGR images in one forward pass. inference_ms is the batch time divided
        evenly across its images."""
        if not images:
            return []
        return self._executor.submit(self._predict_batch, images, conf).result()

    def _predict_batch(self, images: list[np.ndarray], conf: float | None) -> list[DetectionResult]:
        started = time.perf_counter()
        results = self.model.predict(images, imgsz=self.imgsz, conf=self.conf if conf is None else conf,
                                     iou=self.iou, device=self.device, half=self.half, verbose=False)
        per_image_ms = round((time.perf_counter() - started) * 1000 / len(images), 1)

        out = []
        for image, result in zip(images, results):
            height, width = image.shape[:2]
            boxes = result.boxes
            corners = boxes.xyxyn.cpu().numpy().clip(0.0, 1.0)
            confidences = boxes.conf.cpu().numpy()
            class_ids = boxes.cls.cpu().numpy().astype(int)
            detections = [
                Detection(int(c), self.names[int(c)], round(float(p), 4), *(round(float(v), 4) for v in box))
                for box, p, c in zip(corners, confidences, class_ids)
            ]
            detections.sort(key=lambda d: d.confidence, reverse=True)
            out.append(DetectionResult(width, height, per_image_ms, detections))
        return out
