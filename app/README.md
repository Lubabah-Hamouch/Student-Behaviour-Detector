# Focal

Focal is a small web app that detects classroom behavior in images, uploaded video and a live camera. A YOLOv8m model, fine-tuned on classroom footage, labels each person as one of five classes: concentrating, distracted, hand raised, phone, or sleeping. A FastAPI backend serves the model, and the interface is plain HTML, CSS and JavaScript with no build step. Video is analysed on the server and played in the browser with the boxes drawn over it, together with a timeline of when each behavior appears. The live mode streams frames from the camera over a WebSocket.

## Run it locally

Requirements: Python 3.12 and, for the pinned setup, an NVIDIA GPU with CUDA 11.8. It was developed and tested on Windows 11 with an RTX 4060 laptop GPU.

From the project root (the folder that contains `app/`, `models/` and `requirements.txt`):

```powershell
python -m venv venv
venv\Scripts\Activate.ps1          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn app.server.main:app --port 8000
```

Then open <http://127.0.0.1:8000>. Starting takes about 15 to 20 seconds, because the model is loaded and warmed up before the server accepts requests. `/docs` lists the API interactively.

`requirements.txt` installs the CUDA 11.8 build of PyTorch. On a machine without a compatible NVIDIA GPU, install a CPU build of `torch` and `torchvision` first. The app falls back to the CPU on its own, but this path is untested and will be much slower (live mode in particular).

Run the tests with `pip install -r requirements-dev.txt` and then `python -m pytest app/tests`. A few tests need a real classroom frame, which is not included (it would show real students), so they are skipped automatically.

## The model file

The server loads `models/best.pt` at startup. If it is missing, the server still starts, and `/api/health` reports why.

- The weights are tracked with Git LFS. After cloning, run `git lfs pull`. A file of a few hundred bytes is an LFS pointer and not the model.
- The training data (frames and source videos) shows real students and is not part of this repository. To train your own model, supply your own labelled frames in YOLO format under `data/dataset/`, together with a `data/raw_frames/frame_mapping.txt` that maps each frame to its source video (the split is made by video).
- Then build the split with `python scripts/prepare_dataset.py` and run `python scripts/train.py`. The best checkpoint is copied to `models/best.pt`, and the metrics shown in the app come from `results/metrics_summary.json`, which the same script writes. See [`scripts/train.py`](../scripts/train.py) for its options.

## Configuration

These environment variables are read at startup. Unset ones use the default.

| Variable | Default | Effect |
|---|---|---|
| `FOCAL_MODEL` | `models/best.pt` | Path to the weights |
| `FOCAL_METRICS` | `results/metrics_summary.json` | Metrics file shown in the "About the model" section |
| `FOCAL_DEVICE` | auto | `0`, `cpu`, and so on. By default CUDA if available, else CPU |
| `FOCAL_IMGSZ` | `640` | Model input size |
| `FOCAL_CONF_MIN` | `0.10` | Lowest confidence the API returns. The slider can go no lower |
| `FOCAL_DEFAULT_CONF` | `0.50` | Initial position of the confidence slider |
| `FOCAL_IOU` | `0.7` | NMS threshold. Matches the value the reported metrics used |
| `FOCAL_MAX_LIVE_SESSIONS` | `2` | Concurrent live camera sessions |
| `FOCAL_MAX_LIVE_FRAME_KB` | `2048` | Largest live frame the server accepts |
| `FOCAL_SOURCE_URL` | unset | Repository link for the header. The "Source" link is hidden when unset |

Example (PowerShell): `$env:FOCAL_DEFAULT_CONF = "0.4"; uvicorn app.server.main:app --port 8000`. On macOS/Linux: `FOCAL_DEFAULT_CONF=0.4 uvicorn app.server.main:app --port 8000`.

Some limits are constants in [`server/config.py`](server/config.py), not environment variables, so changing them means editing that file: images up to 25 MB and 50 megapixels; videos up to 200 MB and 180 seconds, analysed at 10 frames per second; at most 4 queued or running video jobs; finished video results kept in memory for one hour.

## Privacy

Uploaded images and live frames are processed in memory and are not stored. An uploaded video is written to a temporary folder while it is being analysed and deleted afterwards.

## Known limitations

The model was trained on five videos of one classroom, and it is evaluated on one held-out video per split, so its scores are modest and noisy. The `sleeping` class is the weakest and fails on the test video, which is why the interface marks it as experimental. Results on other scenes, camera angles or close-up webcams may differ a lot. [`docs/LIMITATIONS.md`](../docs/LIMITATIONS.md) covers the dataset, the split, the evaluation numbers and the `sleeping` analysis, and the app serves it at `/limitations`.

## Browser support

Tested in Chrome only (headless Chrome 153, on Windows). The other browsers are expected to work but are untested: Firefox and Safari have not been tried. The code has a fallback for browsers without `requestVideoFrameCallback`, and that fallback was exercised by removing the API in Chrome, not in a real Firefox or Safari. Live mode also needs `getUserMedia`, which browsers allow only on `localhost` or over HTTPS, and it was tested with a simulated camera, not a physical webcam. Video has to be in a format the browser can play, and an MP4 encoded as H.264 is the safe choice.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service and model status |
| `GET /api/model` | Classes, definitions and evaluation summary |
| `POST /api/detect/image` | Detections for one image |
| `POST /api/detect/video` | Start a video analysis job |
| `GET /api/jobs/{id}` and `/result` | Job progress and the per-frame detections |
| `DELETE /api/jobs/{id}` | Cancel a job or release its result |
| `WS /ws/live` | Live frames in, detections out |
| `GET /limitations` | The limitations document, rendered |

## Layout

```
app/
  server/   FastAPI app: main.py, config.py, inference.py, video_jobs.py, routes/
  web/      index.html, css/, js/ (modes/ for image, video and live), fonts/
  tests/    API, page and live-socket tests, plus ws_live_check.py for a manual live check
```
