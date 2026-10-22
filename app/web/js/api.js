// Thin client for the Focal API.

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(url, options = {}) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("Could not reach the server.", 0);
  }
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d) => d.msg).join(", ");
    } catch { /* keep the generic message */ }
    throw new ApiError(message, response.status);
  }
  return response.json();
}

export const getModel = () => request("/api/model");

/** Start a video job. Uses XMLHttpRequest because fetch cannot report upload progress. */
export function submitVideo(file, { sampleFps, onProgress = () => {}, signal } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/detect/video?sample_fps=${encodeURIComponent(sampleFps)}`);
    xhr.responseType = "json";
    xhr.upload.onprogress = (event) => event.lengthComputable && onProgress(event.loaded / event.total);
    xhr.onload = () => {
      if (xhr.status === 202 && xhr.response) return resolve(xhr.response);
      const detail = xhr.response?.detail;
      const message = typeof detail === "string" ? detail
        : Array.isArray(detail) ? detail.map((d) => d.msg).join(", ") : `Upload failed (${xhr.status}).`;
      reject(new ApiError(message, xhr.status));
    };
    xhr.onerror = () => reject(new ApiError("Could not reach the server.", 0));
    xhr.onabort = () => reject(new DOMException("Aborted", "AbortError"));
    signal?.addEventListener("abort", () => xhr.abort());
    const body = new FormData();
    body.append("file", file);
    xhr.send(body);
  });
}

export const getJob = (jobId, { signal } = {}) => request(`/api/jobs/${jobId}`, { signal });
export const getJobResult = (jobId, { signal } = {}) => request(`/api/jobs/${jobId}/result`, { signal });

/** Cancel a running job or release a finished one. Best effort: failures are ignored. */
export function discardJob(jobId) {
  fetch(`/api/jobs/${jobId}`, { method: "DELETE", keepalive: true }).catch(() => {});
}

export function detectImage(file, { signal } = {}) {
  const body = new FormData();
  body.append("file", file);
  return request("/api/detect/image", { method: "POST", body, signal });
}
