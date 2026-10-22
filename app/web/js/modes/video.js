// Video mode. The browser plays the original file; the server only analyses it. Per-frame detections come back as
// JSON and are drawn on a canvas over the player, synced to the playhead.
//
// Flow: load the file in the <video> first (so an unplayable codec fails fast, before any upload), upload it,
// poll the job with a progress bar, fetch the result, then play with the boxes and the behavior timeline.

import { ApiError, discardJob, getJob, getJobResult, submitVideo } from "../api.js";
import { formatTime } from "../timeline.js";

const MAX_BYTES = 200 * 1024 * 1024;
const MAX_SECONDS = 180;
const SAMPLE_FPS = 10; // frames analysed per second of video
const POLL_MS = 500;
const LOAD_TIMEOUT_MS = 20000;

const CODEC_MESSAGE =
  "This browser can't play that video, so it can't be shown here. Use an MP4 encoded as H.264, or a WebM.";

const abortError = () => new DOMException("Aborted", "AbortError");

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    const id = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => { clearTimeout(id); reject(abortError()); }, { once: true });
  });
}

/** Load a file into a <video> and wait for its first frame, translating media errors into plain language. */
function loadVideo(video, url, signal) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => finish(new Error("The video took too long to load.")), LOAD_TIMEOUT_MS);
    const onData = () => finish();
    const onError = () => {
      if (!video.getAttribute("src")) return; // fired by clearing the source, not by a real failure
      const messages = { 3: "The browser could not decode that video. The file may be damaged.", 4: CODEC_MESSAGE };
      finish(new Error(messages[video.error?.code] ?? "The video could not be loaded."));
    };
    const onAbort = () => finish(abortError());
    function finish(error) {
      clearTimeout(timer);
      video.removeEventListener("loadeddata", onData);
      video.removeEventListener("error", onError);
      signal?.removeEventListener("abort", onAbort);
      error ? reject(error) : resolve();
    }
    video.addEventListener("loadeddata", onData);
    video.addEventListener("error", onError);
    signal?.addEventListener("abort", onAbort);
    video.preload = "auto";
    video.src = url;
    video.load();
  });
}

/** Index of the frame whose time is closest to t (times is sorted ascending). */
function nearestIndex(times, t) {
  let lo = 0;
  let hi = times.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid] < t) lo = mid + 1;
    else hi = mid;
  }
  return lo > 0 && t - times[lo - 1] <= times[lo] - t ? lo - 1 : lo;
}

export class VideoMode {
  /**
   * @param {{video: HTMLVideoElement, playButton: HTMLButtonElement, timeLabel: HTMLElement, fileInfo: HTMLElement}} els
   * @param {{stage: object, panel: object, overlay: object, timeline: object}} parts
   */
  constructor(els, { stage, panel, overlay, timeline }) {
    this.els = els;
    Object.assign(this, { stage, panel, overlay, timeline });
    this.token = 0; // bumped by every reset, so stale async work can tell it has been superseded
    this.controller = null;
    this.jobId = null;
    this.objectUrl = null;
    this.data = null;
    this.lastIndex = -1;
    this.rvfc = null;
    this.raf = null;

    const { video, playButton } = els;
    playButton.addEventListener("click", () => this.toggle());
    overlay.onClick = () => this.toggle();
    video.addEventListener("seeked", () => this.data && this.applyTime(video.currentTime));
    video.addEventListener("timeupdate", () => this.data && this.applyTime(video.currentTime));
    video.addEventListener("play", () => {
      this.syncButton();
      if (!("requestVideoFrameCallback" in video)) this.frameLoop();
    });
    video.addEventListener("pause", () => this.syncButton());
    video.addEventListener("ended", () => this.syncButton());
  }

  /** Stop everything and drop the current video. The caller decides what appears on the stage afterwards. */
  reset() {
    this.token += 1;
    this.controller?.abort();
    this.controller = null;
    if (this.jobId) discardJob(this.jobId);
    this.jobId = null;
    this.stopSync();
    const { video, fileInfo, timeLabel } = this.els;
    video.pause();
    video.removeAttribute("src");
    video.load();
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
    this.objectUrl = null;
    this.data = null;
    this.lastIndex = -1;
    this.overlay.clear();
    this.timeline.clear();
    this.panel.clear();
    this.panel.setEnabled(false);
    fileInfo.textContent = "";
    timeLabel.textContent = `${formatTime(0)} / ${formatTime(0)}`;
    this.syncButton();
  }

  fail(message) {
    this.reset();
    this.panel.setStatus("Could not analyse");
    this.stage.show({ state: "error", error: message });
  }

  async open(file) {
    this.reset();
    const token = this.token;
    const controller = new AbortController();
    this.controller = controller;
    const { signal } = controller;
    const alive = () => token === this.token;
    const { video, fileInfo } = this.els;

    if (file.size > MAX_BYTES) return this.fail("That video is larger than 200 MB.");

    fileInfo.textContent = file.name;
    this.panel.setStatus("Preparing video…");
    this.objectUrl = URL.createObjectURL(file);
    this.stage.show({ state: "busy", media: "video", status: { title: "Preparing video", sub: file.name } });
    this.stage.reveal();

    try {
      await loadVideo(video, this.objectUrl, signal);
      if (!video.videoWidth) throw new Error(CODEC_MESSAGE); // audio only, or a video track the browser cannot decode
      if (Number.isFinite(video.duration) && video.duration > MAX_SECONDS) {
        throw new Error(`That video is longer than ${MAX_SECONDS / 60} minutes.`);
      }
      fileInfo.textContent = `${file.name} · ${video.videoWidth} × ${video.videoHeight} · ${formatTime(video.duration)}`;
      this.overlay.resize();

      this.stage.setStatus({ title: "Uploading", sub: "0%", progress: 0 });
      this.panel.setStatus("Uploading…");
      const job = await submitVideo(file, {
        sampleFps: SAMPLE_FPS,
        signal,
        onProgress: (p) => alive() && this.stage.setStatus({ title: "Uploading", sub: `${Math.round(p * 100)}%`, progress: p }),
      });
      if (!alive()) return discardJob(job.job_id);
      this.jobId = job.job_id;

      const result = await this.waitForResult(job.job_id, signal, alive);
      if (!result || !alive()) return;
      discardJob(job.job_id); // this page holds the result now, so the server can drop its copy
      this.jobId = null;
      this.ready(result);
    } catch (error) {
      if (error.name === "AbortError" || !alive()) return;
      this.fail(error.message);
    }
  }

  async waitForResult(jobId, signal, alive) {
    for (;;) {
      const job = await getJob(jobId, { signal });
      if (!alive()) return null;
      if (job.status === "done") break;
      if (job.status === "failed") throw new ApiError(job.error || "The analysis failed.", 500);
      if (job.status === "cancelled") return null;
      if (job.status === "queued") {
        this.stage.setStatus({ title: "Waiting for the model", sub: "Queued" });
      } else {
        const known = job.frames_total > 0;
        this.stage.setStatus({
          title: "Analysing video",
          sub: known ? `Frame ${job.frames_done} of ${job.frames_total} · ${Math.round(job.progress * 100)}%` : `Frame ${job.frames_done}`,
          progress: known ? job.progress : null,
        });
        this.panel.setStatus(known ? `Analysing ${Math.round(job.progress * 100)}%` : "Analysing…");
      }
      await sleep(POLL_MS, signal);
    }
    return getJobResult(jobId, { signal });
  }

  ready(result) {
    const { video } = this.els;
    const times = Float64Array.from(result.frames, (f) => f.t);
    const frames = result.frames.map((f) => f.detections);
    const duration = Number.isFinite(video.duration) ? video.duration : result.duration;
    this.data = { times, frames, duration };

    this.stage.show({ state: "ready", media: "video" });
    this.overlay.resize();
    this.timeline.setData({ times, frames, duration });
    this.panel.setEnabled(true);
    this.startSync();
    this.applyTime(video.currentTime, true);
    this.syncButton();
  }

  // ---- playback and sync --------------------------------------------------------------------------------

  toggle() {
    const { video } = this.els;
    if (!this.data) return;
    if (video.ended) video.currentTime = 0;
    if (video.paused) video.play().catch(() => {});
    else video.pause();
  }

  seek(seconds) {
    this.els.video.currentTime = seconds;
  }

  syncButton() {
    const { video, playButton } = this.els;
    playButton.disabled = !this.data;
    playButton.textContent = video.ended ? "Replay" : video.paused ? "Play" : "Pause";
  }

  /** Show the detections for the analysed frame nearest to media time t. */
  applyTime(t, force = false) {
    const data = this.data;
    if (!data) return;
    this.timeline.setPosition(t);
    this.els.timeLabel.textContent = `${formatTime(t)} / ${formatTime(data.duration)}`;
    const index = nearestIndex(data.times, t);
    if (index === this.lastIndex && !force) return;
    this.lastIndex = index;
    this.overlay.update(data.frames[index]);
    this.panel.update(data.frames[index], formatTime(t));
  }

  /** Preferred: requestVideoFrameCallback reports the exact media time of every frame the browser presents. */
  startSync() {
    const { video } = this.els;
    this.stopSync();
    if (!("requestVideoFrameCallback" in video)) return; // fallback: frameLoop() runs while playing, plus seeked/timeupdate
    const tick = (_now, metadata) => {
      this.applyTime(metadata.mediaTime);
      this.rvfc = video.requestVideoFrameCallback(tick);
    };
    this.rvfc = video.requestVideoFrameCallback(tick);
  }

  /** Fallback for browsers without requestVideoFrameCallback: follow currentTime every animation frame while playing. */
  frameLoop() {
    cancelAnimationFrame(this.raf);
    const { video } = this.els;
    const step = () => {
      if (!this.data || video.paused || video.ended) return;
      this.applyTime(video.currentTime);
      this.raf = requestAnimationFrame(step);
    };
    this.raf = requestAnimationFrame(step);
  }

  stopSync() {
    const { video } = this.els;
    if (this.rvfc !== null) video.cancelVideoFrameCallback?.(this.rvfc);
    cancelAnimationFrame(this.raf);
    this.rvfc = null;
    this.raf = null;
  }
}
