// The stage: one dark area that shows the drop zone, the current image / video / live camera, a progress state,
// or an error. Every mode drives it through show(), so only one thing is ever visible.

export class Stage {
  constructor(els) {
    this.els = els;
  }

  /**
   * @param {{state: "empty"|"busy"|"ready"|"error", media?: "image"|"video"|"live"|null,
   *          status?: {title: string, sub?: string, progress?: number|null, cancellable?: boolean}|null,
   *          error?: string, action?: string}} view
   *   busy: the media (if any) is shown dimmed, with either a thin indeterminate line or, if `status` is given,
   *         a status block
   *   ready: the media is shown; for video the player controls appear, for live the live bar
   *   error: `action` labels the button under the message
   */
  show({ state, media = null, status = null, error = "", action = "Choose another file" }) {
    const { stage, dropzone, imageMedia, videoMedia, liveMedia, progressLine, statusBlock, errorBox, errorText, errorButton,
            actions, player, liveBar } = this.els;
    const hasMedia = (state === "busy" || state === "ready") && media !== null;
    stage.dataset.state = state;
    stage.dataset.media = media ?? "";
    dropzone.hidden = state !== "empty";
    imageMedia.hidden = !(hasMedia && media === "image");
    videoMedia.hidden = !(hasMedia && media === "video");
    liveMedia.hidden = !(hasMedia && media === "live");
    progressLine.hidden = !(state === "busy" && !status && media !== null);
    statusBlock.hidden = !(state === "busy" && status);
    errorBox.hidden = state !== "error";
    player.hidden = !(state === "ready" && media === "video");
    liveBar.hidden = !(state === "ready" && media === "live");
    actions.hidden = state === "empty" || media === "live"; // the file name and "Choose another" do not apply to a camera
    if (state === "error") {
      errorText.textContent = error;
      errorButton.textContent = action;
    }
    if (state === "busy" && status) this.setStatus(status);
  }

  /** Update the busy status block without changing what is visible. */
  setStatus({ title, sub = "", progress = null, cancellable = true }) {
    const { statusTitle, statusSub, statusBar, statusMeter, cancelButton } = this.els;
    statusTitle.textContent = title;
    statusSub.textContent = sub;
    statusMeter.dataset.indeterminate = String(progress === null);
    statusBar.style.width = progress === null ? "" : `${Math.round(Math.min(Math.max(progress, 0), 1) * 100)}%`;
    cancelButton.hidden = !cancellable;
  }

  /** If the stage is not fully on screen (the hero sits above it), scroll the workspace to the top of the window. */
  reveal() {
    const { top, bottom } = this.els.stage.getBoundingClientRect();
    if (bottom > window.innerHeight - 24 || top < 0) {
      document.querySelector(".workspace").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
}
