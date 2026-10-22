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

export function detectImage(file, { signal } = {}) {
  const body = new FormData();
  body.append("file", file);
  return request("/api/detect/image", { method: "POST", body, signal });
}
