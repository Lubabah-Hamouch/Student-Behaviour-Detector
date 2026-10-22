"""Video detection: start a job, poll it, fetch the per-frame detections."""
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from .. import config
from ..deps import get_detector, get_jobs
from ..schemas import JobStatus, VideoJobCreated, VideoResult
from ..video_jobs import JobManager, probe_video

router = APIRouter(prefix="/api")


@router.post("/detect/video", response_model=VideoJobCreated, status_code=202,
             dependencies=[Depends(get_detector)])
async def submit_video(
    file: UploadFile = File(...),
    sample_fps: float = Query(config.DEFAULT_SAMPLE_FPS, ge=1, le=config.MAX_SAMPLE_FPS,
                              description="Frames analysed per second of video."),
    jobs: JobManager = Depends(get_jobs),
):
    if not (file.content_type or "").startswith("video/"):
        raise HTTPException(status_code=415, detail="Upload a video file (MP4, MOV, WebM, AVI or MKV).")
    jobs.prune()
    if jobs.pending_count() >= config.MAX_PENDING_JOBS:
        raise HTTPException(status_code=429, detail="The server is busy with other videos. Try again shortly.")

    suffix = Path(file.filename or "").suffix.lower()
    path = jobs.new_upload_path(suffix if suffix in config.VIDEO_SUFFIXES else ".mp4")
    limit = config.MAX_VIDEO_MB * 1024 * 1024
    try:
        size = 0
        with open(path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"Video is larger than {config.MAX_VIDEO_MB} MB.")
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        try:
            info = await run_in_threadpool(probe_video, path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if info.duration is not None and info.duration > config.MAX_VIDEO_SECONDS:
            raise HTTPException(status_code=413,
                                detail=f"Video is longer than {config.MAX_VIDEO_SECONDS} seconds "
                                       f"({info.duration:.0f} s).")
    except BaseException:
        path.unlink(missing_ok=True)
        raise

    job = jobs.create(path, info, sample_fps)
    return VideoJobCreated(
        job_id=job.id,
        status=job.status,
        width=info.width,
        height=info.height,
        duration=round(info.duration, 3) if info.duration is not None else None,
        native_fps=round(info.fps, 3),
        sample_fps=sample_fps,
        frames_total=job.frames_total,
    )


def _job_or_404(jobs: JobManager, job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job.")
    return job


@router.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str, jobs: JobManager = Depends(get_jobs)):
    job = _job_or_404(jobs, job_id)
    total = job.frames_total
    progress = 1.0 if job.status == "done" else (min(job.frames_done / total, 0.99) if total else 0.0)
    return JobStatus(job_id=job.id, status=job.status, progress=round(progress, 3),
                     frames_done=job.frames_done, frames_total=total, error=job.error)


@router.delete("/jobs/{job_id}", status_code=204)
def discard_job(job_id: str, jobs: JobManager = Depends(get_jobs)):
    """Cancel a queued or running job, or release a finished job's result."""
    if not jobs.discard(job_id):
        raise HTTPException(status_code=404, detail="Unknown or expired job.")


@router.get("/jobs/{job_id}/result", response_model=VideoResult)
def job_result(job_id: str, jobs: JobManager = Depends(get_jobs)):
    job = _job_or_404(jobs, job_id)
    if job.status == "failed":
        raise HTTPException(status_code=409, detail=f"Job failed: {job.error}")
    if job.status != "done" or job.result is None:
        raise HTTPException(status_code=409, detail=f"Job is not finished (status: {job.status}).")
    return job.result
