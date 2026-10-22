import { getModel } from "./api.js";
import { renderModelInfo } from "./modelinfo.js";
import { Overlay } from "./overlay.js";
import { Panel } from "./panel.js";
import { ImageMode } from "./modes/image.js";

const $ = (selector) => document.querySelector(selector);

async function init() {
  let model;
  try {
    model = await getModel();
  } catch (error) {
    $("#panel-status").textContent = "Service unavailable";
    $(".dropzone-sub").textContent = error.message;
    $("#choose-file").disabled = true;
    $("#model-lede").textContent = "Model details are unavailable while the service is down.";
    return;
  }

  renderModelInfo(model);

  if (model.source_url) {
    const link = $("#source-link");
    link.href = model.source_url;
    link.hidden = false;
  }

  const overlay = new Overlay($("#overlay"), model.classes.map((c) => c.name), (det) => panel.setHighlight(det ? det.name : null));
  const panel = new Panel($(".panel"), model.classes, {
    threshold: model.default_confidence,
    onThreshold: (threshold) => overlay.setThreshold(threshold),
    onHover: (name) => overlay.setHighlight(name),
  });
  overlay.setThreshold(model.default_confidence);

  const image = new ImageMode(
    {
      stage: $("#stage"),
      dropzone: $("#dropzone"),
      media: $("#media"),
      img: $("#media-img"),
      progress: $("#stage-progress"),
      errorBox: $("#stage-error"),
      errorText: $("#stage-error-text"),
      actions: $("#stage-actions"),
      fileInfo: $("#file-info"),
      fileInput: $("#file-input"),
      chooseButtons: [$("#choose-file"), $("#error-choose"), $("#replace-btn")],
      clearButton: $("#clear-btn"),
    },
    { panel, overlay },
  );
  image.setState("empty");
}

init();
