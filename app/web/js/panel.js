// The "Detections" side panel: one row per class (count and mean-confidence bar) and the confidence slider.

export const displayName = (name) => name.replace(/_/g, " ");
export const sentenceCase = (name) => displayName(name).replace(/^./, (c) => c.toUpperCase());

export class Panel {
  /**
   * @param {HTMLElement} root  the panel element
   * @param {{id:number,name:string,experimental:boolean}[]} classes
   * @param {{threshold:number, onThreshold:(t:number)=>void, onHover:(name:string|null)=>void}} options
   */
  constructor(root, classes, { threshold, onThreshold, onHover }) {
    this.list = root.querySelector("#class-list");
    this.status = root.querySelector("#panel-status");
    this.slider = root.querySelector("#conf-slider");
    this.value = root.querySelector("#conf-value");
    this.classes = classes;
    this.threshold = threshold;
    this.detections = [];
    this.rows = new Map();

    for (const cls of classes) {
      const row = document.createElement("li");
      row.className = "class-row";
      row.dataset.class = cls.name;
      row.dataset.empty = "true";
      row.style.setProperty("--c", `var(--c-${cls.name})`);
      row.innerHTML = `
        <span class="swatch" aria-hidden="true"></span>
        <span class="class-name">${sentenceCase(cls.name)}${
          cls.experimental ? ' <span class="tag" title="Less reliable than the other classes. See Limitations.">experimental</span>' : ""
        }</span>
        <span class="class-count mono">0</span>
        <span class="class-meter"><span class="bar" aria-hidden="true"><i></i></span><span class="class-conf mono">&ndash;</span></span>`;
      row.addEventListener("pointerenter", () => onHover(cls.name));
      row.addEventListener("pointerleave", () => onHover(null));
      this.list.append(row);
      this.rows.set(cls.name, row);
    }

    this.slider.min = "0.10";
    this.slider.value = String(threshold);
    this.value.textContent = threshold.toFixed(2);
    this.slider.addEventListener("input", () => {
      this.threshold = Number(this.slider.value);
      this.value.textContent = this.threshold.toFixed(2);
      this.render();
      onThreshold(this.threshold);
    });
  }

  setEnabled(enabled) {
    this.slider.disabled = !enabled;
  }

  setStatus(text) {
    this.status.textContent = text;
  }

  /** Mark a class as highlighted (others dimmed), or clear with null. */
  setHighlight(name) {
    for (const [cls, row] of this.rows) row.dataset.dim = String(name !== null && cls !== name);
  }

  /** @param {{name:string, confidence:number}[]} detections all detections returned by the API */
  update(detections, meta = "") {
    this.detections = detections;
    this.meta = meta;
    this.render();
  }

  clear() {
    this.detections = [];
    this.meta = "";
    this.render();
  }

  render() {
    const visible = this.detections.filter((d) => d.confidence >= this.threshold);
    for (const [name, row] of this.rows) {
      const own = visible.filter((d) => d.name === name);
      const mean = own.length ? own.reduce((sum, d) => sum + d.confidence, 0) / own.length : 0;
      row.dataset.empty = String(own.length === 0);
      row.querySelector(".class-count").textContent = String(own.length);
      row.querySelector(".class-conf").textContent = own.length ? mean.toFixed(2) : "–";
      row.querySelector(".bar > i").style.width = `${Math.round(mean * 100)}%`;
    }
    if (this.detections.length || this.meta) {
      const total = visible.length;
      this.setStatus(`${total} ${total === 1 ? "detection" : "detections"}${this.meta ? ` · ${this.meta}` : ""}`);
    }
  }
}
