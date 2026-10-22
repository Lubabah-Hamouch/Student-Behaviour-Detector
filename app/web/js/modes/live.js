// Live mode: the camera plays in a <video>; downscaled JPEG frames go to the server over a WebSocket, one in
// flight at a time, and each reply's detections are drawn over the live picture.
//
// Protocol (see app/server/routes/live.py): client -> server a binary message, 4-byte big-endian frame id then the
// JPEG; server -> client a JSON message per processed frame.

const CAPTURE_WIDTH = 640; // frames are downscaled to this width before encoding
const JPEG_QUALITY = 0.8;
const FPS_WINDOW_MS = 2000;
const CHIP_REFRESH_MS = 250;
const HINT_SECONDS = 9;
const MAX_FRAME_AGE_MS = 150; // a prepared frame older than this (after a stall) is dropped for a fresh one

const CLOSE_MESSAGES = {
  1013: "The server is already running its maximum number of live sessions. Try again in a moment.",
  1009: "The server rejected a frame as too large. Try again, or use a lower camera resolution.",
  1011: "The detection service is unavailable right now.",
  1006: "Lost the connection to the server.",
};

function cameraMessage(error) {
  switch (error?.name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Camera access was blocked. Allow it in your browser's site settings, then try again.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No camera was found on this device.";
    case "NotReadableError":
    case "AbortError":
      return "The camera is in use by another application, or could not be started.";
    default:
      return "The camera could not be started.";
  }
}

const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
};

export class LiveMode {
  /**
   * @param {{video: HTMLVideoElement, chip: HTMLElement, hint: HTMLElement, hintDismiss: HTMLElement}} els
   * @param {{stage: object, panel: object, overlay: object}} parts
   */
  constructor(els, { stage, panel, overlay }) {
    this.els = els;
    Object.assign(this, { stage, panel, overlay });
    this.token = 0; // bumped by every reset, so stale async work can tell it has been superseded
    this.stream = null;
    this.socket = null;
    this.running = false;
    this.pending = null; // the one frame in flight: {seq, started}
    this.seq = 0;
    this.replies = []; // recent {at, latency}
    this.lastChip = 0;
    this.hintTimer = null;
    this.capture = document.createElement("canvas");
    els.hintDismiss.addEventListener("click", () => this.hideHint());
  }

  /** Stop the camera and the connection and clear the overlay. The caller decides what appears afterwards. */
  reset() {
    this.token += 1;
    this.running = false;
    this.pending = null; // the frame in flight
    this.prepared = null; // the next frame, already captured and encoded
    this.preparing = false;
    if (this.socket) {
      this.socket.onopen = this.socket.onmessage = this.socket.onclose = this.socket.onerror = null;
      try { this.socket.close(1000); } catch { /* already closed */ }
      this.socket = null;
    }
    if (this.stream) {
      this.stream.getTracks().forEach((track) => { track.onended = null; track.stop(); });
      this.stream = null;
    }
    this.els.video.srcObject = null;
    this.replies = [];
    this.hideHint();
    this.els.chip.textContent = "";
    delete this.els.chip.dataset.latency;
    delete this.els.chip.dataset.fps;
    this.overlay.clear();
    this.panel.clear();
    this.panel.setEnabled(false);
  }

  fail(message) {
    this.reset();
    this.panel.setStatus("Live stopped");
    this.stage.show({ state: "error", media: "live", error: message, action: "Try again" });
  }

  async start() {
    this.reset();
    const token = this.token;
    const alive = () => token === this.token;
    const { video } = this.els;

    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      return this.fail("Camera access needs a secure connection (HTTPS, or localhost).");
    }
    this.panel.setStatus("Waiting for the camera…");
    this.stage.show({ state: "busy", media: null, status: { title: "Waiting for camera access", sub: "Allow the camera in your browser to continue." } });
    this.stage.reveal();

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
    } catch (error) {
      if (alive()) this.fail(cameraMessage(error));
      return;
    }
    if (!alive()) return stream.getTracks().forEach((track) => track.stop()); // cancelled while the prompt was open
    this.stream = stream;
    stream.getVideoTracks()[0].onended = () => alive() && this.fail("The camera was disconnected.");

    video.srcObject = stream;
    try {
      await video.play();
      if (!video.videoWidth) await new Promise((resolve) => video.addEventListener("loadedmetadata", resolve, { once: true }));
    } catch {
      if (alive()) this.fail("The camera could not be started.");
      return;
    }
    if (!alive()) return;

    this.panel.setStatus("Connecting…");
    this.stage.show({ state: "busy", media: "live", status: { title: "Connecting to the detector", cancellable: true } });
    this.overlay.resize();
    this.connect(alive);
  }

  connect(alive) {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${scheme}://${location.host}/ws/live`);
    socket.binaryType = "arraybuffer";
    this.socket = socket;
    this.firstReply = true;

    socket.onopen = () => {
      if (!alive()) return;
      this.running = true;
      this.panel.setStatus("Starting detection…");
      this.prefetch();
    };
    socket.onmessage = (event) => alive() && this.onReply(JSON.parse(event.data));
    socket.onclose = (event) => {
      if (!alive()) return;
      this.fail(CLOSE_MESSAGES[event.code] ?? `The live connection closed (code ${event.code}).`);
    };
  }

  // ---- the frame loop -----------------------------------------------------------------------------------
  // One frame is on the wire at a time. While it is being analysed, the next one is already captured and
  // encoded, so it goes out the moment the reply arrives instead of after another capture and encode.

  /** Resolves when the browser presents a new video frame, so the same picture is never prepared twice. */
  nextVideoFrame() {
    const { video } = this.els;
    return new Promise((resolve) => {
      if ("requestVideoFrameCallback" in video) video.requestVideoFrameCallback(() => resolve());
      else requestAnimationFrame(() => resolve());
    });
  }

  /** Capture and encode a fresh frame into this.prepared. */
  async prefetch() {
    if (!this.running || this.preparing) return;
    const { video } = this.els;
    const token = this.token;
    this.preparing = true;
    try {
      await this.nextVideoFrame();
      if (token !== this.token || !this.running || video.readyState < 2 || !video.videoWidth) return;
      const capturedAt = performance.now();
      const width = Math.min(CAPTURE_WIDTH, video.videoWidth);
      const height = Math.round((video.videoHeight * width) / video.videoWidth);
      this.capture.width = width;
      this.capture.height = height;
      this.capture.getContext("2d").drawImage(video, 0, 0, width, height);
      const blob = await new Promise((resolve) => this.capture.toBlob(resolve, "image/jpeg", JPEG_QUALITY));
      if (token !== this.token || !this.running || !blob) return;
      const jpeg = await blob.arrayBuffer();
      if (token !== this.token || !this.running) return;
      this.prepared = { jpeg, capturedAt };
    } finally {
      if (token === this.token) this.preparing = false;
    }
    this.trySend();
    if (!this.prepared && !this.pending) this.prefetch(); // nothing was sent or kept (an unusable frame): try again
  }

  /** Send the prepared frame if nothing is in flight, then start preparing the next one. */
  trySend() {
    if (!this.running || this.pending || !this.prepared) return;
    if (this.socket?.readyState !== WebSocket.OPEN) return;
    const { jpeg, capturedAt } = this.prepared;
    this.prepared = null;
    if (performance.now() - capturedAt > MAX_FRAME_AGE_MS) return void this.prefetch(); // stale after a stall: take a fresh one

    const seq = (this.seq = (this.seq + 1) >>> 0);
    const message = new Uint8Array(4 + jpeg.byteLength);
    new DataView(message.buffer).setUint32(0, seq);
    message.set(new Uint8Array(jpeg), 4);
    this.pending = { seq, started: capturedAt };
    this.socket.send(message);
    this.prefetch();
  }

  onReply(message) {
    const pending = this.pending;
    this.pending = null;
    if (message.error || !pending || message.seq !== pending.seq) return this.trySend(); // skip an unreadable frame
    const now = performance.now();
    const latency = now - pending.started; // frame age at send + network + model + decode, until the reply is in hand

    if (this.firstReply) {
      this.firstReply = false;
      this.stage.show({ state: "ready", media: "live" });
      this.overlay.resize();
      this.panel.setEnabled(true);
      this.showHint();
    }
    this.overlay.update(message.detections);
    this.panel.update(message.detections, `${Math.round(latency)} ms`);
    this.recordStats(now, latency);
    this.trySend();
  }

  recordStats(now, latency) {
    this.replies.push({ at: now, latency });
    while (this.replies.length && now - this.replies[0].at > FPS_WINDOW_MS) this.replies.shift();
    if (now - this.lastChip < CHIP_REFRESH_MS) return;
    this.lastChip = now;
    const window = this.replies;
    const span = Math.max(now - window[0].at, 1);
    const fps = window.length > 1 ? ((window.length - 1) * 1000) / span : 0;
    const typical = median(window.map((r) => r.latency));
    const { chip } = this.els;
    chip.textContent = `${Math.round(typical)} ms · ${fps.toFixed(0)} fps`;
    chip.dataset.latency = typical.toFixed(1);
    chip.dataset.fps = fps.toFixed(1);
  }

  // ---- the "best results" hint ----------------------------------------------------------------------------

  showHint() {
    const { hint } = this.els;
    hint.hidden = false;
    delete hint.dataset.hiding;
    clearTimeout(this.hintTimer);
    this.hintTimer = setTimeout(() => this.hideHint(), HINT_SECONDS * 1000);
  }

  hideHint() {
    const { hint } = this.els;
    clearTimeout(this.hintTimer);
    if (hint.hidden) return;
    hint.dataset.hiding = "true"; // fades out, then leaves the layout
    setTimeout(() => { if (hint.dataset.hiding) hint.hidden = true; }, 400);
  }
}
