"""API tests. Run from the project root with the project venv:  python -m pytest app/tests"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.server import config
from app.server.main import app

CLASSES = ["distracted", "concentrating", "hand_raised", "phone", "sleeping"]
SAMPLE_IMAGE = config.PROJECT_ROOT / "data" / "dataset" / "images" / "image147.jpg"  # frame from the test video


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # runs the lifespan: loads the model once for the module
        yield c


def post_image(client, content=b"", name="x.jpg", content_type="image/jpeg"):
    return client.post("/api/detect/image", files={"file": (name, content, content_type)})


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["classes"] == CLASSES
    assert body["model"]["weights"] == "models/best.pt"
    assert body["model"]["architecture"] == "YOLOv8m"
    assert body["device"]


def test_model_info_matches_metrics_file(client):
    r = client.get("/api/model")
    assert r.status_code == 200
    body = r.json()
    assert [c["name"] for c in body["classes"]] == CLASSES
    assert all(c["definition"] for c in body["classes"])
    assert {c["name"] for c in body["classes"] if c["experimental"]} == {"sleeping"}

    on_disk = json.loads(config.METRICS_PATH.read_text(encoding="utf-8"))
    assert body["metrics"]["test"]["mAP50"] == pytest.approx(on_disk["test"]["mAP50"])
    assert body["metrics"]["val"]["mAP50-95"] == pytest.approx(on_disk["val"]["mAP50-95"])
    assert body["metrics"]["test"]["per_class"]["sleeping"]["instances"] == 118
    assert body["metrics"]["run"] == "full_run_v1"


def test_detect_image_real_frame(client):
    r = post_image(client, SAMPLE_IMAGE.read_bytes(), SAMPLE_IMAGE.name)
    assert r.status_code == 200
    body = r.json()
    assert (body["width"], body["height"]) == (832, 464)
    assert body["inference_ms"] > 0
    assert len(body["detections"]) > 0
    assert any(d["confidence"] >= 0.5 for d in body["detections"])
    for d in body["detections"]:
        assert d["name"] == CLASSES[d["class_id"]]
        assert config.CONF_MIN <= d["confidence"] <= 1
        b = d["box"]
        assert 0 <= b["x1"] < b["x2"] <= 1 and 0 <= b["y1"] < b["y2"] <= 1
    assert sum(body["counts"].values()) == len(body["detections"])
    confidences = [d["confidence"] for d in body["detections"]]
    assert confidences == sorted(confidences, reverse=True)


def test_rejects_non_image_content_type(client):
    assert post_image(client, b"hello", "x.txt", "text/plain").status_code == 415


def test_rejects_corrupt_image(client):
    assert post_image(client, b"this is not a jpeg").status_code == 400


def test_rejects_empty_file(client):
    assert post_image(client, b"").status_code == 400


def test_rejects_oversized_upload(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_IMAGE_MB", 0)  # any non-empty upload is now over the limit
    assert post_image(client, SAMPLE_IMAGE.read_bytes()).status_code == 413


def test_rejects_too_many_pixels(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_IMAGE_PIXELS", 1000)
    assert post_image(client, SAMPLE_IMAGE.read_bytes()).status_code == 413


def test_missing_model_reports_503(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MODEL_PATH", tmp_path / "missing.pt")
    with TestClient(app) as c:
        health = c.get("/api/health")
        assert health.status_code == 503
        assert "missing.pt" in health.json()["detail"]
        assert c.get("/api/model").status_code == 503
        assert post_image(c, SAMPLE_IMAGE.read_bytes()).status_code == 503
