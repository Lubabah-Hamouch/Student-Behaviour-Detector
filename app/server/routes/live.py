"""Live camera detection over a WebSocket.

Protocol
  client -> server  binary message: a 4-byte big-endian frame id, then a JPEG image.
  server -> client  JSON text message per processed frame:
      {"seq": <frame id>, "width": w, "height": h, "inference_ms": model time, "server_ms": time from receiving the
       frame to sending this reply, "dropped": frames discarded so far, "detections": [...]}
    or, if a frame cannot be decoded:  {"seq": <frame id>, "error": "..."}

The server keeps only the newest unprocessed frame. If the client sends faster than the model runs, older frames
are dropped (and counted) instead of queueing, so latency stays bounded. A client that waits for each reply
before sending the next frame never drops any.
"""
import asyncio
import time

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket
from starlette.concurrency import run_in_threadpool

from .. import config
from ..schemas import detection_out

router = APIRouter()


def _infer(detector, jpeg: bytes):
    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return None
    return detector.predict(image)


@router.websocket("/ws/live")
async def live(ws: WebSocket):
    await ws.accept()
    detector = getattr(ws.app.state, "detector", None)
    if detector is None:
        await ws.close(code=1011, reason="Model unavailable")
        return
    if getattr(ws.app.state, "live_sessions", 0) >= config.MAX_LIVE_SESSIONS:
        await ws.close(code=1013, reason="Too many live sessions, try again later")
        return
    ws.app.state.live_sessions += 1

    newest: list = []  # at most one pending (received_at, bytes)
    arrived = asyncio.Event()
    closed = asyncio.Event()
    dropped = 0

    async def receive() -> None:
        nonlocal dropped
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    return
                data = message.get("bytes")
                if data is None:
                    continue  # ignore text messages
                if len(data) > config.MAX_LIVE_FRAME_KB * 1024:
                    await ws.close(code=1009, reason="Frame too large")
                    return
                if newest:
                    dropped += 1
                newest[:] = [(time.perf_counter(), data)]
                arrived.set()
        finally:
            closed.set()
            arrived.set()

    async def process() -> None:
        while True:
            await arrived.wait()
            arrived.clear()
            if not newest:
                if closed.is_set():
                    return
                continue
            received_at, data = newest.pop()
            if len(data) <= 4:
                await ws.send_json({"seq": None, "error": "Empty frame."})
                continue
            seq = int.from_bytes(data[:4], "big")
            result = await run_in_threadpool(_infer, detector, data[4:])
            if result is None:
                await ws.send_json({"seq": seq, "error": "The frame is not a readable image."})
                continue
            await ws.send_json({
                "seq": seq,
                "width": result.width,
                "height": result.height,
                "inference_ms": result.inference_ms,
                "server_ms": round((time.perf_counter() - received_at) * 1000, 1),
                "dropped": dropped,
                "detections": [detection_out(d).model_dump() for d in result.detections],
            })

    receiver = asyncio.create_task(receive())
    processor = asyncio.create_task(process())
    try:
        await asyncio.wait({receiver, processor}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in (receiver, processor):
            task.cancel()
        await asyncio.gather(receiver, processor, return_exceptions=True)
        ws.app.state.live_sessions -= 1
