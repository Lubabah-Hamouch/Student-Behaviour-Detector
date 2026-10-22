// Image mode: choose or drop an image, send it to the API, draw the result.

import { detectImage } from "../api.js";

const MAX_BYTES = 25 * 1024 * 1024;

export class ImageMode {
  /**
   * @param {object} els  DOM references (see main.js)
   * @param {{panel: object, overlay: object}} parts
   */
  constructor(els, { panel, overlay }) {
    this.els = els;
    this.panel = panel;
    this.overlay = overlay;
    this.objectUrl = null;
    this.controller = null;

    const { stage, fileInput } = els;
    els.chooseButtons.forEach((button) => button.addEventListener("click", () => fileInput.click()));
    fileInput.addEventListener("change", () => {
      const [file] = fileInput.files;
      fileInput.value = ""; // allow choosing the same file again
      if (file) this.open(file);
    });
    els.clearButton.addEventListener("click", () => this.reset());

    // Drag and drop anywhere on the stage. Drops elsewhere on the page must not navigate away from the app.
    window.addEventListener("dragover", (event) => event.preventDefault());
    window.addEventListener("drop", (event) => event.preventDefault());
    let depth = 0;
    stage.addEventListener("dragenter", (event) => {
      event.preventDefault();
      depth += 1;
      stage.dataset.dragover = "true";
    });
    stage.addEventListener("dragleave", () => {
      depth = Math.max(0, depth - 1);
      if (depth === 0) delete stage.dataset.dragover;
    });
    stage.addEventListener("drop", (event) => {
      event.preventDefault();
      depth = 0;
      delete stage.dataset.dragover;
      const [file] = event.dataTransfer?.files ?? [];
      if (file) this.open(file);
    });

    document.addEventListener("paste", (event) => {
      const file = [...(event.clipboardData?.files ?? [])].find((f) => f.type.startsWith("image/"));
      if (file) this.open(file);
    });
  }

  setState(state) {
    this.els.stage.dataset.state = state;
    const { dropzone, media, progress, errorBox, actions } = this.els;
    dropzone.hidden = state !== "empty";
    media.hidden = !(state === "loading" || state === "result");
    progress.hidden = state !== "loading";
    errorBox.hidden = state !== "error";
    actions.hidden = state === "empty";
  }

  /** If the stage is not fully on screen (the hero sits above it), scroll the workspace to the top of the window. */
  revealStage() {
    const { top, bottom } = this.els.stage.getBoundingClientRect();
    if (bottom > window.innerHeight - 24 || top < 0) {
      document.querySelector(".workspace").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  fail(message) {
    this.els.errorText.textContent = message;
    this.overlay.clear();
    this.panel.clear();
    this.panel.setEnabled(false);
    this.panel.setStatus("Detection failed");
    this.els.fileInfo.textContent = "";
    this.setState("error");
  }

  reset() {
    this.controller?.abort();
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
    this.objectUrl = null;
    this.els.img.removeAttribute("src");
    this.overlay.clear();
    this.panel.clear();
    this.panel.setEnabled(false);
    this.panel.setStatus("No image yet");
    this.els.fileInfo.textContent = "";
    this.setState("empty");
  }

  async open(file) {
    if (file.type.startsWith("video/")) return this.fail("Video isn't available yet. Choose an image for now.");
    if (!file.type.startsWith("image/")) return this.fail("That file is not an image. Use a JPEG, PNG or WebP.");
    if (file.size > MAX_BYTES) return this.fail("That image is larger than 25 MB.");

    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;

    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
    this.objectUrl = URL.createObjectURL(file);
    const { img } = this.els;
    img.alt = `Uploaded image: ${file.name}`;
    img.src = this.objectUrl;
    this.overlay.clear();
    this.panel.clear();
    this.panel.setEnabled(false);
    this.panel.setStatus("Detecting…");
    this.els.fileInfo.textContent = file.name;
    this.setState("loading");

    try {
      await img.decode();
      this.revealStage();
    } catch {
      return this.fail("The browser could not read that image.");
    }
    if (controller.signal.aborted) return;
    this.els.fileInfo.textContent = `${file.name} · ${img.naturalWidth} × ${img.naturalHeight}`;

    try {
      const result = await detectImage(file, { signal: controller.signal });
      if (controller.signal.aborted) return;
      this.setState("result");
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
