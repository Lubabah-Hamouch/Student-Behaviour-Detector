// The "About the model" section: class legend and a deliberately modest evaluation summary, from /api/model.

import { sentenceCase } from "./panel.js";

const fmt = (value, digits = 2) => Number(value).toFixed(digits);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function renderModelInfo(model) {
  const { architecture } = model.model;
  document.querySelector("#model-lede").textContent =
    `${architecture}, trained on five videos of one classroom and scored on a held-out video it never saw during training.`;

  // Class legend: swatch, name, definition.
  const legend = document.querySelector("#legend");
  legend.replaceChildren();
  for (const cls of model.classes) {
    const row = el("li");
    row.style.setProperty("--c", `var(--c-${cls.name})`);
    const swatch = el("span", "swatch");
    swatch.setAttribute("aria-hidden", "true");
    const name = el("span", "legend-name", sentenceCase(cls.name));
    if (cls.experimental) {
      const tag = el("span", "tag", "experimental");
      tag.title = "Less reliable than the other classes. See Limitations.";
      name.append(tag);
    }
    row.append(swatch, name, el("span", "legend-def", cls.definition));
    legend.append(row);
  }

  const side = document.querySelector("#model-side");
  const metrics = model.metrics;
  if (!metrics) return;
  side.hidden = false;

  document.querySelector("#metric-value").textContent = fmt(metrics.test.mAP50);

  const facts = document.querySelector("#metric-facts");
  facts.replaceChildren();
  for (const [label, value] of [
    ["Test mAP50-95", fmt(metrics.test["mAP50-95"])],
    ["Validation mAP50", fmt(metrics.val.mAP50)],
  ]) {
    const row = el("div");
    row.append(el("dt", "", label), el("dd", "mono", value));
    facts.append(row);
  }

  // A plain-language note that names the weakest class instead of burying it in a table.
  const perClass = Object.entries(metrics.test.per_class);
  const [weakest, weakestMetrics] = perClass.reduce((low, cur) => (cur[1].mAP50 < low[1].mAP50 ? cur : low));
  const flagged = model.classes.find((c) => c.name === weakest)?.experimental;
  document.querySelector("#metric-note").textContent =
    `One small test video, so read these scores as indicative. ${sentenceCase(weakest)} is the weakest class ` +
    `(mAP50 ${fmt(weakestMetrics.mAP50)})${flagged ? " and is marked experimental" : ""}.`;

  const body = document.querySelector("#per-class-body");
  body.replaceChildren();
  for (const cls of model.classes) {
    const m = metrics.test.per_class[cls.name];
    if (!m) continue;
    const row = el("tr");
    row.append(
      el("th", "", sentenceCase(cls.name)),
      el("td", "num mono", String(m.instances ?? "")),
      el("td", "num mono", fmt(m.precision)),
      el("td", "num mono", fmt(m.recall)),
      el("td", "num mono", fmt(m.mAP50)),
    );
    row.firstChild.scope = "row";
    body.append(row);
  }
}
