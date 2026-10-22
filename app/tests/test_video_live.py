"""Video-job and live-WebSocket tests. Run from the project root:  python -m pytest app/tests"""
import time

import cv2
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.server import config
from app.server.main import create_app

SAMPLE_IMAGE = config.PROJECT_ROOT / "data" / "dataset" / "images" / "image147.jpg"
VIDEO_FPS, VIDEO_FRAMES = 10, 20  # a 2 s clip


@pytest.fixture(scope="module")
def video_bytes(tmp_path_factory):
    """A tiny 2 s MP4 made from a real dataset frame."""
    frame = cv2.imread(str(SAMPLE_IMAGE))
    path = tmp_path_factory.mktemp("video") / "clip.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), VIDEO_FPS, (frame.shape[1], frame.shape[0]))
    for _ in range(VIDEO_FRAMES):
        writer.write(frame)
    writer.release()
    return path.read_bytes()


def submit(client, content, name="clip.mp4", content_type="video/mp4", **params):
    return client.post("/api/detect/video", params=params, files={"file": (name, content, content_type)})


def wait_until_done(client, job_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get(f"/api/jobs/{job_id}").json()
        if status["status"] in ("done", "failed"):
            return status
        time.sleep(0.2)
    pytest.fail("job did not finish in time")


def jpeg_message(seq: int, image=None) -> bytes:
    image = cv2.imread(str(SAMPLE_IMAGE)) if image is None else image
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    assert ok
    return seq.to_bytes(4, "big") + buf.tobytes()


# ---- video -------------------------------------------------------------------------------------------------

def test_video_job_end_to_end(client, video_bytes):
    created = submit(client, video_bytes, sample_fps=5)
    assert created.status_code == 202
    body = created.json()
    assert body["status"] == "queued" and body["job_id"]
    assert (body["width"], body["height"]) == (832, 464)
    assert body["sample_fps"] == 5 and body["frames_total"] == 10

    status = wait_until_done(client, body["job_id"])
    assert status["status"] == "done" and status["progress"] == 1.0

    result = client.get(f"/api/jobs/{body['job_id']}/result")
    assert result.status_code == 200
    r = result.json()
    assert r["summary"]["frames_processed"] == len(r["frames"]) == 10
    assert r["sample_fps"] == pytest.approx(5.0, abs=0.1)
    times = [f["t"] for f in r["frames"]]
    assert times == sorted(times) and times[0] == 0.0
    assert times[1] == pytest.approx(0.2, abs=0.01)
    assert r["duration"] == pytest.approx(2.0, abs=0.15)
    assert r["summary"]["detections_total"] == sum(len(f["detections"]) for f in r["frames"]) > 0
    for f in r["frames"]:
        for d in f["detections"]:
            b = d["box"]
            assert 0 <= b["x1"] < b["x2"] <= 1 and 0 <= b["y1"] < b["y2"] <= 1


def test_video_upload_is_deleted_after_processing(client, video_bytes):
    job_id = submit(client, video_bytes, sample_fps=2).json()["job_id"]
    wait_until_done(client, job_id)
    assert not list(config.UPLOAD_DIR.glob("*"))


def test_video_rejects_non_video_content_type(client):
    assert submit(client, b"hello", "x.txt", "text/plain").status_code == 415


def test_video_rejects_unreadable_video(client):
    assert submit(client, b"definitely not a video").status_code == 400


def test_video_rejects_empty_file(client):
    assert submit(client, b"").status_code == 400


def test_video_rejects_bad_sample_fps(client, video_bytes):
    assert submit(client, video_bytes, sample_fps=0).status_code == 422
    assert submit(client, video_bytes, sample_fps=500).status_code == 422


def test_video_rejects_oversized_upload(client, video_bytes, monkeypatch):
    monkeypatch.setattr(config, "MAX_VIDEO_MB", 0)
    assert submit(client, video_bytes).status_code == 413


def test_video_rejects_too_long(client, video_bytes, monkeypatch):
    monkeypatch.setattr(config, "MAX_VIDEO_SECONDS", 1)
    assert submit(client, video_bytes).status_code == 413


def test_video_busy_returns_429(client, video_bytes, monkeypatch):
    monkeypatch.setattr(config, "MAX_PENDING_JOBS", 0)
    assert submit(client, video_bytes).status_code == 429


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/api/jobs/nope/result").status_code == 404


def test_result_before_done_is_409(client, video_bytes, monkeypatch):
    jobs = client.app.state.jobs
    monkeypatch.setattr(jobs, "_queue", type("Sink", (), {"put": lambda self, job: None})())  # never processed
    job_id = submit(client, video_bytes).json()["job_id"]
    status = client.get(f"/api/jobs/{job_id}").json()
    assert status["status"] == "queued" and status["progress"] == 0
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 409


# ---- batch inference ---------------------------------------------------------------------------------------

def test_batch_prediction_matches_single(client):
    detector = client.app.state.detector
    image = cv2.imread(str(SAMPLE_IMAGE))
    single = detector.predict(image)
    batch = detector.predict_batch([image, image])
    assert len(batch) == 2
    for result in batch:
        assert len(result.detections) == len(single.detections)
        for a, b in zip(result.detections, single.detections):
            assert a.class_id == b.class_id
            assert a.confidence == pytest.approx(b.confidence, abs=0.02)
            assert a.x1 == pytest.approx(b.x1, abs=0.01)


# ---- live --------------------------------------------------------------------------------------------------

def test_live_frames_round_trip(client):
    with client.websocket_connect("/ws/live") as ws:
        for seq in (7, 8, 9):
            ws.send_bytes(jpeg_message(seq))
            msg = ws.receive_json()
            assert msg["seq"] == seq
            assert (msg["width"], msg["height"]) == (832, 464)
            assert msg["inference_ms"] > 0 and msg["server_ms"] >= msg["inference_ms"]
            assert msg["dropped"] == 0
            assert any(d["confidence"] >= 0.5 for d in msg["detections"])


def test_live_bad_frame_returns_error_and_keeps_going(client):
    with client.websocket_connect("/ws/live") as ws:
        ws.send_bytes((3).to_bytes(4, "big") + b"not a jpeg")
        assert ws.receive_json() == {"seq": 3, "error": "The frame is not a readable image."}
        ws.send_bytes(jpeg_message(4))
        assert ws.receive_json()["seq"] == 4


def test_live_rejects_oversized_frame(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_LIVE_FRAME_KB", 1)
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/ws/live") as ws:
            ws.send_bytes(jpeg_message(1))
            ws.receive_json()
    assert closed.value.code == 1009


def test_live_limits_sessions(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_LIVE_SESSIONS", 0)
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/ws/live") as ws:
            ws.receive_json()
    assert closed.value.code == 1013


def test_live_session_counter_returns_to_zero(client):
    with client.websocket_connect("/ws/live") as ws:
        ws.send_bytes(jpeg_message(1))
        ws.receive_json()
    time.sleep(0.3)
    assert client.app.state.live_sessions == 0


def test_live_without_model_closes(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MODEL_PATH", tmp_path / "missing.pt")
    with TestClient(create_app()) as c:
        with pytest.raises(WebSocketDisconnect) as closed:
            with c.websocket_connect("/ws/live") as ws:
                ws.receive_json()
        assert closed.value.code == 1011
