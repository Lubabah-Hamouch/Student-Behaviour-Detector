// Getting a file into the app: the file dialog, drag and drop onto the stage, and paste.
// It only hands the file on; deciding what to do with it (image or video) is up to the caller.

const VIDEO_EXTENSIONS = /\.(mp4|m4v|mov|webm|mkv|avi)$/i;

/** "image", "video", or null for anything else. Falls back to the extension when the browser gives no MIME type. */
export function kindOf(file) {
  if (file.type.startsWith("image/")) return "image";
  if (file.type.startsWith("video/") || (!file.type && VIDEO_EXTENSIONS.test(file.name))) return "video";
  return null;
}

export function setupIntake({ stage, fileInput, chooseButtons, onFile }) {
  chooseButtons.forEach((button) => button.addEventListener("click", () => fileInput.click()));
  fileInput.addEventListener("change", () => {
    const [file] = fileInput.files;
    fileInput.value = ""; // allow choosing the same file again
    if (file) onFile(file);
  });

  // Drop anywhere on the stage. A drop elsewhere on the page must not navigate away from the app.
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
    if (file) onFile(file);
  });

  document.addEventListener("paste", (event) => {
    const file = [...(event.clipboardData?.files ?? [])].find((f) => kindOf(f));
    if (file) onFile(file);
  });
}
