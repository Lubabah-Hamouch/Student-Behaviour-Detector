"""Video jobs: an uploaded video is scanned on a background thread and its per-frame detections are kept in memory.

The browser plays the original file itself and draws these detections over it, so nothing is re-encoded.
"""
import math
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import cv2

from . import config
from .inference import Detector
from .schemas import VideoFrame, VideoResult, VideoSummary, detection_out


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    frame_count: int  # 0 if the container does not report one
    duration: float | None


def probe_video(path: Path) -> VideoInfo:
    """Open a video and decode its first frame. Raises ValueError if it cannot be read."""
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError("The file is not a readable video.")
        ok, frame = cap.read()
        if not ok or frame is None:
            raise ValueError("The file is not a readable video.")
        height, width = frame.shape[:2]
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not 1.0 <= fps <= 240.0:  # missing or nonsensical in some containers
            fps = 30.0
        count = max(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), 0)
        return VideoInfo(width, height, float(fps), count, count / fps if count else None)
    finally:
        cap.release()


@dataclass
class Job:
    id: str
    path: Path
    sample_fps: float  # requested
    info: VideoInfo
    frames_total: int
    status: str = "queued"
    frames_done: int = 0
    error: str | None = None
    result: VideoResult | None = None
    created: float = 0.0
    finished: float | None = None
    cancel_requested: bool = False


class Cancelled(Exception):
    """Raised inside the worker when a job was cancelled."""


class JobManager:
    def __init__(self, detector: Detector, upload_dir: Path):
        self.detector = detector
        self.upload_dir = upload_dir
        self._jobs: dict[str, Job] = {}
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        for stale in self.upload_dir.iterdir():  # leftovers from a previous run
            if stale.is_file():
                stale.unlink(missing_ok=True)
        self._thread = threading.Thread(target=self._run, name="video-jobs", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=5)

    def create(self, path: Path, info: VideoInfo, sample_fps: float) -> Job:
        step = max(info.fps / sample_fps, 1.0)
        total = math.ceil(info.frame_count / step) if info.frame_count else 0
        job = Job(uuid.uuid4().hex[:12], path, sample_fps, info, total, created=time.time())
        self._jobs[job.id] = job
        self._queue.put(job)
        return job

    def new_upload_path(self, suffix: str) -> Path:
        return self.upload_dir / f"{uuid.uuid4().hex}{suffix}"

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def discard(self, job_id: str) -> bool:
        """Forget a job. A queued or running job is cancelled (the worker stops at the next batch); a finished
        job just has its result released. Returns False if the id is unknown."""
        job = self._jobs.pop(job_id, None)
        if job is None:
            return False
        job.cancel_requested = True
        return True

    def pending_count(self) -> int:
        return sum(j.status in ("queued", "running") for j in list(self._jobs.values()))

    def prune(self) -> None:
        """Forget finished jobs older than the retention time."""
        cutoff = time.time() - config.JOB_TTL_SECONDS
        for job_id, job in list(self._jobs.items()):
            if job.finished is not None and job.finished < cutoff:
                del self._jobs[job_id]

    # -- worker -------------------------------------------------------------------------------------------

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            if job is None:
                return
            self._process(job)

    def _process(self, job: Job) -> None:
        if job.cancel_requested:  # cancelled while it was still queued
            job.status = "cancelled"
            job.path.unlink(missing_ok=True)
            job.finished = time.time()
            return
        job.status = "running"
        started = time.time()
        cap = cv2.VideoCapture(str(job.path))
        try:
            native_fps = job.info.fps
            step = max(native_fps / job.sample_fps, 1.0)  # native frames between analysed frames
            frames: list[VideoFrame] = []
            batch: list = []
            batch_t: list[float] = []
            inference_ms: list[float] = []
            detections_total = 0
            index, next_sample = 0, 0.0

            def flush() -> None:
                nonlocal detections_total
                if job.cancel_requested:
                    raise Cancelled
                for t, result in zip(batch_t, self.detector.predict_batch(batch)):
                    frames.append(VideoFrame(t=round(t, 3), detections=[detection_out(d) for d in result.detections]))
                    inference_ms.append(result.inference_ms)
                    detections_total += len(result.detections)
                job.frames_done = len(frames)
                batch.clear()
                batch_t.clear()

            while cap.grab():
                t = index / native_fps
                if t > config.MAX_VIDEO_SECONDS:
                    raise ValueError(f"Video is longer than {config.MAX_VIDEO_SECONDS} seconds.")
                if index >= next_sample:
                    ok, frame = cap.retrieve()
                    if ok:
                        batch.append(frame)
                        batch_t.append(t)
                        next_sample += step
                        if len(batch) == config.VIDEO_BATCH:
                            flush()
                index += 1
            if batch:
                flush()
            if not frames:
                raise ValueError("No frames could be read from the video.")

            job.result = VideoResult(
                job_id=job.id,
                width=job.info.width,
                height=job.info.height,
                duration=round(index / native_fps, 3),
                native_fps=round(native_fps, 3),
                sample_fps=round(native_fps / step, 3),
                frames=frames,
                summary=VideoSummary(
                    frames_processed=len(frames),
                    detections_total=detections_total,
                    inference_ms_mean=round(sum(inference_ms) / len(inference_ms), 1),
                    processing_seconds=round(time.time() - started, 1),
                ),
            )
            job.frames_total = len(frames)
            job.status = "done"
        except Cancelled:
            job.status = "cancelled"
        except Exception as exc:  # report the failure through the job, never crash the worker
            job.status = "failed"
            job.error = str(exc)
        finally:
            cap.release()
            job.path.unlink(missing_ok=True)
            job.finished = time.time()
