// Image mode: send an image to the API and draw the result.

import { detectImage } from "../api.js";

const MAX_BYTES = 25 * 1024 * 1024;

export class ImageMode {
  /**
   * @param {{img: HTMLImageElement, fileInfo: HTMLElement}} els
   * @param {{stage: import("../stage.js").Stage, panel: object, overlay: object}} parts
   */
  constructor(els, { stage, panel, overlay }) {
    this.els = els;
    this.stage = stage;
    this.panel = panel;
    this.overlay = overlay;
    this.objectUrl = null;
    this.controller = null;
  }

  /** Drop everything this mode is showing. The caller decides what appears on the stage afterwards. */
  reset() {
    this.controller?.abort();
    this.controller = null;
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
    this.objectUrl = null;
    this.els.img.removeAttribute("src");
    this.overlay.clear();
    this.panel.clear();
    this.panel.setEnabled(false);
    this.els.fileInfo.textContent = "";
  }

  fail(message) {
    this.reset();
    this.panel.setStatus("Detection failed");
    this.stage.show({ state: "error", error: message });
  }

  async open(file) {
    if (file.size > MAX_BYTES) return this.fail("That image is larger than 25 MB.");

    this.reset();
    const controller = new AbortController();
    this.controller = controller;
    this.objectUrl = URL.createObjectURL(file);
    const { img, fileInfo } = this.els;
    img.alt = `Uploaded image: ${file.name}`;
    img.src = this.objectUrl;
    this.panel.setStatus("Detecting…");
    fileInfo.textContent = file.name;
    this.stage.show({ state: "busy", media: "image" });

    try {
      await img.decode();
    } catch {
      return this.fail("The browser could not read that image.");
    }
    if (controller.signal.aborted) return;
    this.stage.reveal();
    fileInfo.textContent = `${file.name} · ${img.naturalWidth} × ${img.naturalHeight}`;

    try {
      const result = await detectImage(file, { signal: controller.signal });
      if (controller.signal.aborted) return;
      this.stage.show({ state: "ready", media: "image" });
      this.overlay.resize(); // the canvas just became visible
      this.overlay.setDetections(result.detections);
      this.panel.setEnabled(true);
      this.panel.update(result.detections, `${Math.round(result.inference_ms)} ms`);
    } catch (error) {
      if (error.name === "AbortError") return;
      this.fail(error.message);
    }
  }
}
