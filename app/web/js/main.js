import { getModel } from "./api.js";
import { kindOf, setupIntake } from "./intake.js";
import { renderModelInfo } from "./modelinfo.js";
import { ImageMode } from "./modes/image.js";
import { LiveMode } from "./modes/live.js";
import { VideoMode } from "./modes/video.js";
import { Overlay } from "./overlay.js";
import { Panel } from "./panel.js";
import { Stage } from "./stage.js";
import { Timeline } from "./timeline.js";

const $ = (selector) => document.querySelector(selector);

const MODES = {
  image: {
    empty: "No image yet",
    title: "Drop an image here",
    sub: "JPEG, PNG or WebP up to 25 MB.",
    accept: "image/jpeg,image/png,image/webp,image/bmp",
  },
  video: {
    empty: "No video yet",
    title: "Drop a video here",
    sub: "MP4, MOV or WebM, up to 3 minutes and 200 MB. It is analysed on the server and played here.",
    accept: "video/mp4,video/quicktime,video/webm,video/x-matroska,.mkv,.avi,.m4v",
  },
  live: {
    empty: "Camera off",
    title: "Use your camera",
    sub: "Point it at a group from a distance, the way a classroom camera would see them. Frames are analysed on the server and are not stored.",
    accept: "",
  },
};

async function init() {
  let model;
  try {
    model = await getModel();
  } catch (error) {
    $("#panel-status").textContent = "Service unavailable";
    $("#dropzone-sub").textContent = error.message;
    $("#choose-file").disabled = true;
    $("#use-camera").disabled = true;
    $("#model-lede").textContent = "Model details are unavailable while the service is down.";
    return;
  }

  renderModelInfo(model);
  if (model.source_url) {
    const link = $("#source-link");
    link.href = model.source_url;
    link.hidden = false;
  }

  const classNames = model.classes.map((c) => c.name);
  const threshold = model.default_confidence;

  const stage = new Stage({
    stage: $("#stage"),
    dropzone: $("#dropzone"),
    imageMedia: $("#media"),
    videoMedia: $("#video-media"),
    liveMedia: $("#live-media"),
    progressLine: $("#stage-progress"),
    statusBlock: $("#stage-status"),
    statusTitle: $("#status-title"),
    statusSub: $("#status-sub"),
    statusBar: $("#status-bar"),
    statusMeter: $("#status-meter"),
    cancelButton: $("#cancel-btn"),
    errorBox: $("#stage-error"),
    errorText: $("#stage-error-text"),
    errorButton: $("#error-choose"),
    actions: $("#stage-actions"),
    player: $("#player"),
    liveBar: $("#live-bar"),
  });

  // Hovering a box highlights its class in the panel, and hovering a panel row emphasises that class's boxes.
  const onBoxHover = (det) => panel.setHighlight(det ? det.name : null);
  const overlays = {
    image: new Overlay($("#overlay"), classNames, onBoxHover),
    video: new Overlay($("#video-overlay"), classNames, onBoxHover),
    live: new Overlay($("#live-overlay"), classNames, onBoxHover),
  };

  const timeline = new Timeline({
    track: $("#timeline-track"),
    canvas: $("#timeline-canvas"),
    playhead: $("#timeline-playhead"),
    hoverLine: $("#timeline-hover"),
    tip: $("#timeline-tip"),
    labels: $("#timeline-labels"),
    classes: model.classes,
    onSeek: (seconds) => video.seek(seconds),
    onToggle: () => video.toggle(),
  });

  const panel = new Panel($(".panel"), model.classes, {
    threshold,
    onThreshold: (t) => {
      Object.values(overlays).forEach((overlay) => overlay.setThreshold(t));
      timeline.setThreshold(t);
    },
    onHover: (name) => Object.values(overlays).forEach((overlay) => overlay.setHighlight(name)),
  });
  [...Object.values(overlays), timeline].forEach((target) => target.setThreshold(threshold));

  const image = new ImageMode({ img: $("#media-img"), fileInfo: $("#file-info") }, { stage, panel, overlay: overlays.image });
  const video = new VideoMode(
    { video: $("#video"), playButton: $("#play-btn"), timeLabel: $("#time-label"), fileInfo: $("#file-info") },
    { stage, panel, overlay: overlays.video, timeline },
  );
  const live = new LiveMode(
    { video: $("#live-video"), chip: $("#live-chip"), hint: $("#live-hint"), hintDismiss: $("#hint-dismiss") },
    { stage, panel, overlay: overlays.live },
  );
  const handlers = { image, video, live };

  // ---- modes ------------------------------------------------------------------------------------------
  let current = "image";
  const fileInput = $("#file-input");

  const showEmpty = () => {
    stage.show({ state: "empty" });
    panel.setStatus(MODES[current].empty);
  };

  function setMode(mode) {
    Object.values(handlers).forEach((handler) => handler.reset());
    current = mode;
    for (const tab of document.querySelectorAll('[role="tab"]')) {
      tab.setAttribute("aria-selected", String(tab.dataset.mode === mode));
    }
    const isLive = mode === "live";
    $("#dropzone-title").textContent = MODES[mode].title;
    $("#dropzone-sub").textContent = MODES[mode].sub;
    $("#choose-file").hidden = isLive;
    const camera = $("#use-camera");
    camera.textContent = isLive ? "Start camera" : "Use camera";
    camera.className = isLive ? "btn btn-light" : "btn btn-outline-light";
    if (!isLive) fileInput.accept = MODES[mode].accept;
    showEmpty();
  }

  function startOver() {
    handlers[current].reset();
    showEmpty();
  }

  async function handleFile(file) {
    const kind = kindOf(file);
    if (!kind) {
      handlers[current].reset();
      panel.setStatus("Nothing to show");
      stage.show({ state: "error", error: "That file is not an image or a video." });
      return;
    }
    if (kind !== current) setMode(kind); // a dropped video switches to the Video tab, and the reverse
    await handlers[kind].open(file);
  }

  for (const tab of document.querySelectorAll('[role="tab"]')) {
    tab.addEventListener("click", () => tab.dataset.mode !== current && setMode(tab.dataset.mode));
  }
  $("#clear-btn").addEventListener("click", startOver);
  $("#cancel-btn").addEventListener("click", startOver);
  $("#stop-btn").addEventListener("click", startOver);
  $("#use-camera").addEventListener("click", () => {
    if (current !== "live") setMode("live");
    live.start(); // starts inside the click, as camera permission prompts require
  });
  $("#error-choose").addEventListener("click", () => (current === "live" ? live.start() : fileInput.click()));
  setupIntake({
    stage: $("#stage"),
    fileInput,
    chooseButtons: [$("#choose-file"), $("#replace-btn")],
    onFile: handleFile,
  });
  setMode("image");
}

init();
