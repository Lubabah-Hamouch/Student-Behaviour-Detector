"""Manual check of the /ws/live endpoint against a running server (not a pytest test).

Feeds frames the way the browser will: downscaled to 640 px wide, JPEG-encoded, one frame in flight at a time.
Frames come from a video file, or from a webcam with --camera.

    python app/tests/ws_live_check.py                                  # 40 frames of a project video
    python app/tests/ws_live_check.py --video data/raw_videos/telephone.mp4 --frames 60
    python app/tests/ws_live_check.py --camera                         # webcam 0
    python app/tests/ws_live_check.py --burst 12                       # send 12 frames back to back
"""
import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import cv2
import websockets

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def frame_source(args):
    """Yield BGR frames, spread across the video (or from the camera)."""
    if args.camera:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise SystemExit("Could not open the camera.")
        while True:
            ok, frame = cap.read()
            if not ok:
                return
            yield frame
    cap = cv2.VideoCapture(str(args.video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    stride = max(total // max(args.frames, 1), 1)
    for index in range(0, total, stride):
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = cap.read()
        if not ok:
            return
        yield frame


def encode(frame, seq: int) -> bytes:
    height, width = frame.shape[:2]
    if width > 640:
        frame = cv2.resize(frame, (640, round(height * 640 / width)), interpolation=cv2.INTER_AREA)
    ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return seq.to_bytes(4, "big") + jpeg.tobytes()


async def one_in_flight(args):
    round_trips, inference, server = [], [], []
    last = None
    async with websockets.connect(args.url, max_size=2**22) as ws:
        for seq, frame in enumerate(frame_source(args)):
            if seq >= args.frames:
                break
            message = encode(frame, seq)
            sent = time.perf_counter()
            await ws.send(message)
            reply = json.loads(await ws.recv())
            rtt = (time.perf_counter() - sent) * 1000
            assert reply["seq"] == seq, reply
            round_trips.append(rtt)
            inference.append(reply["inference_ms"])
            server.append(reply["server_ms"])
            last = reply
            if seq < 6:
                top = ", ".join(f"{d['name']} {d['confidence']:.2f}" for d in reply["detections"][:3])
                print(f"frame {seq:3d}  {len(message) / 1024:5.1f} KB  round trip {rtt:6.1f} ms  "
                      f"inference {reply['inference_ms']:5.1f} ms  server {reply['server_ms']:5.1f} ms  "
                      f"{len(reply['detections']):2d} detections  [{top}]")
    n = len(round_trips)
    print(f"\n{n} frames, one in flight (client JPEG-encodes each frame; round trip = send until reply)")
    print(f"  round trip   median {statistics.median(round_trips):6.1f} ms   "
          f"p95 {sorted(round_trips)[int(0.95 * (n - 1))]:6.1f} ms   max {max(round_trips):6.1f} ms")
    print(f"  inference    median {statistics.median(inference):6.1f} ms     server median {statistics.median(server):6.1f} ms")
    print(f"  throughput   {1000 / statistics.mean(round_trips):.1f} frames/s   dropped by server: {last['dropped']}")
    if last:
        print("  last frame:", last["width"], "x", last["height"], "->",
              {d["name"] for d in last["detections"] if d["confidence"] >= 0.3} or "no detections >= 0.30")


async def burst(args):
    """Send frames without waiting for replies; the server should drop the stale ones and answer the newest."""
    frames = [encode(f, i) for i, f in zip(range(args.burst), frame_source(args))]
    async with websockets.connect(args.url, max_size=2**22) as ws:
        started = time.perf_counter()
        for message in frames:
            await ws.send(message)
        replies = []
        while True:
            try:
                replies.append(json.loads(await asyncio.wait_for(ws.recv(), timeout=1.5)))
            except asyncio.TimeoutError:
                break
        print(f"sent {len(frames)} frames back to back, got {len(replies)} replies in "
              f"{(time.perf_counter() - started) * 1000:.0f} ms")
        print("  reply seq ids:", [r["seq"] for r in replies], "| dropped (cumulative):", replies[-1]["dropped"])
        print("  the last frame sent was id", len(frames) - 1, "and the last reply is for id", replies[-1]["seq"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="ws://127.0.0.1:8000/ws/live")
    parser.add_argument("--video", type=Path, default=PROJECT_ROOT / "data" / "raw_videos" / "sleeping+variety.mp4")
    parser.add_argument("--camera", action="store_true", help="use webcam 0 instead of a video file")
    parser.add_argument("--frames", type=int, default=40)
    parser.add_argument("--burst", type=int, default=0, help="send this many frames without waiting for replies")
    args = parser.parse_args()
    asyncio.run(burst(args) if args.burst else one_in_flight(args))


if __name__ == "__main__":
    main()
