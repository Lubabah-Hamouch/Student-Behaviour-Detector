// The behavior timeline: one thin row per class with a tick wherever that class is detected, a playhead,
// and click / drag / keyboard seeking. It doubles as the video's scrubber.

import { displayName } from "./panel.js";

const ROW_HEIGHT = 10;
const ROW_GAP = 6;

/** 83.4 -> "1:23.4" */
export function formatTime(seconds) {
  const s = Math.max(0, seconds);
  const minutes = Math.floor(s / 60);
  return `${minutes}:${(s - minutes * 60).toFixed(1).padStart(4, "0")}`;
}

export class Timeline {
  /**
   * @param {{track: HTMLElement, canvas: HTMLCanvasElement, playhead: HTMLElement, hoverLine: HTMLElement,
   *          tip: HTMLElement, labels: HTMLElement, classes: {name: string}[],
   *          onSeek: (seconds: number) => void, onToggle: () => void}} options
   */
  constructor({ track, canvas, playhead, hoverLine, tip, labels, classes, onSeek, onToggle }) {
    Object.assign(this, { track, canvas, playhead, hoverLine, tip, classes, onSeek, onToggle });
    this.ctx = canvas.getContext("2d");
    this.times = new Float64Array(0);
    this.frames = []; // per frame: [{name, confidence}, ...]
    this.duration = 0;
    this.interval = 0.1;
    this.threshold = 0.5;
    this.dragging = false;

    const style = getComputedStyle(document.documentElement);
    this.baseColor = style.getPropertyValue("--line").trim() || "#DAD6CC";
    this.colors = classes.map((c) => style.getPropertyValue(`--c-${c.name}`).trim() || "#888888");

    labels.replaceChildren(
      ...classes.map((c) => {
        const li = document.createElement("li");
        li.textContent = displayName(c.name);
        li.style.setProperty("--c", `var(--c-${c.name})`);
        return li;
      }),
    );
    canvas.style.height = `${classes.length * ROW_HEIGHT + (classes.length - 1) * ROW_GAP}px`;
    track.style.height = canvas.style.height;

    new ResizeObserver(() => this.resize()).observe(canvas);
    track.addEventListener("pointerdown", (event) => {
      if (!this.duration) return;
      this.dragging = true;
      track.setPointerCapture(event.pointerId);
      this.seekTo(event);
    });
    track.addEventListener("pointermove", (event) => {
      if (!this.duration) return;
      if (this.dragging) this.seekTo(event);
      this.showHover(event);
    });
    const release = () => (this.dragging = false);
    track.addEventListener("pointerup", release);
    track.addEventListener("pointercancel", release);
    track.addEventListener("pointerleave", () => this.hideHover());
    track.addEventListener("keydown", (event) => this.keydown(event));
  }

  /** @param {{times: Float64Array, frames: object[][], duration: number}} data */
  setData({ times, frames, duration }) {
    this.times = times;
    this.frames = frames;
    this.duration = duration;
    this.interval = times.length > 1 ? (times[times.length - 1] - times[0]) / (times.length - 1) : 0.1;
    this.track.setAttribute("aria-valuemax", duration.toFixed(1));
    this.setPosition(0);
    this.draw();
  }

  clear() {
    this.setData({ times: new Float64Array(0), frames: [], duration: 0 });
  }

  setThreshold(threshold) {
    this.threshold = threshold;
    this.draw();
  }

  setPosition(seconds) {
    const fraction = this.duration ? Math.min(Math.max(seconds / this.duration, 0), 1) : 0;
    this.playhead.style.left = `${(fraction * 100).toFixed(3)}%`;
    this.track.setAttribute("aria-valuenow", seconds.toFixed(1));
    this.track.setAttribute("aria-valuetext", `${formatTime(seconds)} of ${formatTime(this.duration)}`);
  }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const { width, height } = this.canvas.getBoundingClientRect();
    this.width = width;
    this.height = height;
    this.canvas.width = Math.max(1, Math.round(width * dpr));
    this.canvas.height = Math.max(1, Math.round(height * dpr));
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.draw();
  }

  /** Runs of consecutive frames that contain `className` at or above the threshold, as [startTime, endTime] pairs. */
  runs(className) {
    const out = [];
    let start = null;
    let last = null;
    for (let i = 0; i < this.frames.length; i++) {
      const present = this.frames[i].some((d) => d.name === className && d.confidence >= this.threshold);
      const t = this.times[i];
      if (present && start !== null && t - last <= this.interval * 1.5) {
        last = t;
      } else {
        if (start !== null) out.push([start, last + this.interval]);
        start = present ? t : null;
        last = present ? t : null;
      }
    }
    if (start !== null) out.push([start, last + this.interval]);
    return out;
  }

  draw() {
    const { ctx, width, height } = this;
    if (!width) return;
    ctx.clearRect(0, 0, width, height);
    this.classes.forEach((cls, row) => {
      const y = row * (ROW_HEIGHT + ROW_GAP);
      ctx.fillStyle = this.baseColor;
      ctx.fillRect(0, y, width, ROW_HEIGHT);
      if (!this.duration) return;
      ctx.fillStyle = this.colors[row];
      for (const [from, to] of this.runs(cls.name)) {
        const x = (from / this.duration) * width;
        const w = Math.max(1.5, ((Math.min(to, this.duration) - from) / this.duration) * width);
        ctx.fillRect(x, y, w, ROW_HEIGHT);
      }
    });
  }

  timeAt(event) {
    const { left, width } = this.track.getBoundingClientRect();
    return Math.min(Math.max((event.clientX - left) / width, 0), 1) * this.duration;
  }

  seekTo(event) {
    this.onSeek(this.timeAt(event));
  }

  showHover(event) {
    const { left, width } = this.track.getBoundingClientRect();
    const x = Math.min(Math.max(event.clientX - left, 0), width);
    this.tip.textContent = formatTime(this.timeAt(event));
    const half = this.tip.offsetWidth / 2;
    this.hoverLine.style.transform = `translateX(${x}px)`;
    this.tip.style.transform = `translateX(${Math.min(Math.max(x, half), width - half)}px) translateX(-50%)`; // stay inside the track
    this.hoverLine.dataset.visible = this.tip.dataset.visible = "true";
  }

  hideHover() {
    delete this.hoverLine.dataset.visible;
    delete this.tip.dataset.visible;
    this.hoverLine.style.transform = this.tip.style.transform = ""; // a hidden element must not widen the page
  }

  keydown(event) {
    if (!this.duration) return;
    const now = Number(this.track.getAttribute("aria-valuenow")) || 0;
    const step = event.shiftKey ? 5 : 1;
    const targets = {
      ArrowLeft: now - step,
      ArrowRight: now + step,
      Home: 0,
      End: this.duration,
    };
    if (event.key in targets) {
      event.preventDefault();
      this.onSeek(Math.min(Math.max(targets[event.key], 0), this.duration));
    } else if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      this.onToggle();
    }
  }
}
