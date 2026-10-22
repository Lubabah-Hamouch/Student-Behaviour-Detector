// Draws detection boxes and label chips on a canvas laid exactly over the displayed media.
// Boxes arrive normalised to [0, 1], so the same detections draw correctly at any display size.

import { displayName } from "./panel.js";

const CHIP_FONT = '500 11.5px "IBM Plex Mono", ui-monospace, Consolas, monospace';
const CHIP_HEIGHT = 18;
const INK = "#1A1C1E";

function luminance(hex) {
  const channel = (i) => {
    const v = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
}

/** White or ink text, whichever has more contrast on this colour. */
function textColorOn(hex) {
  const l = luminance(hex);
  const white = 1.05 / (l + 0.05);
  const ink = (l + 0.05) / (luminance(INK) + 0.05);
  return white >= ink ? "#FFFFFF" : INK;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

const overlaps = (a, b, pad = 3) =>
  a.x < b.x + b.w + pad && a.x + a.w + pad > b.x && a.y < b.y + b.h + pad && a.y + a.h + pad > b.y;

export class Overlay {
  /**
   * @param {HTMLCanvasElement} canvas
   * @param {string[]} classNames
   * @param {(det: object|null) => void} onHover  called when the pointer moves over a box (or leaves all boxes)
   */
  constructor(canvas, classNames, onHover = () => {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.onHover = onHover;
    this.detections = [];
    this.threshold = 0.5;
    this.highlight = null; // class name emphasised from the side panel
    this.hovered = null; // detection under the pointer

    const style = getComputedStyle(document.documentElement);
    this.colors = {};
    this.textColors = {};
    for (const name of classNames) {
      const color = style.getPropertyValue(`--c-${name}`).trim() || "#888888";
      this.colors[name] = color;
      this.textColors[name] = textColorOn(color);
    }

    new ResizeObserver(() => this.resize()).observe(canvas);
    canvas.addEventListener("pointermove", (event) => this.pointerMove(event));
    canvas.addEventListener("pointerleave", () => this.setHovered(null));
    document.fonts?.addEventListener?.("loadingdone", () => this.draw());
  }

  setDetections(detections) {
    this.detections = detections;
    this.setHovered(null);
    this.draw();
  }

  setThreshold(threshold) {
    this.threshold = threshold;
    this.setHovered(null);
    this.draw();
  }

  setHighlight(name) {
    this.highlight = name;
    this.draw();
  }

  clear() {
    this.detections = [];
    this.hovered = null;
    this.draw();
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

  visible() {
    return this.detections.filter((d) => d.confidence >= this.threshold);
  }

  rectOf(d) {
    const { x1, y1, x2, y2 } = d.box;
    return { x: x1 * this.width, y: y1 * this.height, w: (x2 - x1) * this.width, h: (y2 - y1) * this.height };
  }

  isEmphasised(d) {
    return d === this.hovered || (this.highlight !== null && d.name === this.highlight);
  }

  isDimmed(d) {
    if (this.highlight !== null) return d.name !== this.highlight;
    return this.hovered !== null && d !== this.hovered;
  }

  setHovered(det) {
    if (det === this.hovered) return;
    this.hovered = det;
    this.onHover(det);
    this.draw();
  }

  pointerMove(event) {
    const bounds = this.canvas.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    const y = event.clientY - bounds.top;
    let best = null;
    let bestArea = Infinity;
    for (const d of this.visible()) {
      const r = this.rectOf(d);
      if (x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h && r.w * r.h < bestArea) {
        best = d;
        bestArea = r.w * r.h;
      }
    }
    this.setHovered(best);
  }

  draw() {
    const { ctx, width, height } = this;
    if (!width) return;
    ctx.clearRect(0, 0, width, height);
    const items = this.visible();
    if (!items.length) return;

    // Boxes: low confidence first so the confident ones sit on top.
    const ascending = [...items].sort((a, b) => a.confidence - b.confidence);
    for (const d of ascending) {
      const r = this.rectOf(d);
      const alpha = this.isDimmed(d) ? 0.28 : 1;
      const weight = this.isEmphasised(d) ? 3 : 2;
      ctx.lineJoin = "round";
      ctx.globalAlpha = alpha * 0.85;
      ctx.strokeStyle = "rgba(255, 255, 255, 0.92)"; // thin halo keeps the stroke readable on any footage
      ctx.lineWidth = weight + 2;
      ctx.strokeRect(r.x, r.y, r.w, r.h);
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = this.colors[d.name];
      ctx.lineWidth = weight;
      ctx.strokeRect(r.x, r.y, r.w, r.h);
    }

    // Label chips: most confident first; a chip that would cover an already placed one is skipped
    // unless its box is emphasised, so busy frames stay legible (hover a box to see its label).
    ctx.globalAlpha = 1;
    ctx.font = CHIP_FONT;
    ctx.textBaseline = "middle";
    const placed = [];
    const descending = [...items].sort((a, b) => b.confidence - a.confidence);
    for (const d of descending) {
      if (this.isDimmed(d)) continue;
      const emphasised = this.isEmphasised(d);
      const r = this.rectOf(d);
      const label = `${displayName(d.name)} ${d.confidence.toFixed(2)}`;
      const w = Math.ceil(ctx.measureText(label).width) + 12;
      const x = Math.min(Math.max(r.x - 1, 0), Math.max(width - w, 0));
      const above = r.y - CHIP_HEIGHT - 3;
      const y = above >= 0 ? above : Math.min(r.y + 3, height - CHIP_HEIGHT);
      const chip = { x, y, w, h: CHIP_HEIGHT };
      if (!emphasised && placed.some((p) => overlaps(chip, p))) continue;
      placed.push(chip);
      ctx.fillStyle = this.colors[d.name];
      roundRect(ctx, chip.x, chip.y, chip.w, chip.h, 3);
      ctx.fill();
      ctx.fillStyle = this.textColors[d.name];
      ctx.fillText(label, chip.x + 6, chip.y + chip.h / 2 + 0.5);
    }
  }
}
