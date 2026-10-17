// The HTTP API (src/kuulas/server.py). Every call returns parsed JSON, or
// throws an Error whose message is the server's own text in the UI language
// (the server picks it from Accept-Language, which the browser sends).

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request(path, options = {}) {
  const headers = typeof options.body === "string" ? { "Content-Type": "application/json" } : {};
  const response = await fetch(path, { ...options, headers: { ...headers, ...options.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(body.error?.text ?? response.statusText, response.status, body);
  }
  return response;
}

const json = async (path, options) => (await request(path, options)).json();
const post = (path, body) => json(path, { method: "POST", body: JSON.stringify(body) });

export const getState = () => json("/api/state");
export const getWords = () => json("/api/words");
/** One edit: the whole project comes back. `coalesce` merges a drag into one undo step. */
export const edit = ({ op, args, label = null, coalesce = null }) =>
  post("/api/edit", { op, args, label, coalesce });
export const command = (name, args = {}) => post("/api/command", { name, args });
export const undo = () => json("/api/undo", { method: "POST" });
export const redo = () => json("/api/redo", { method: "POST" });
export const transport = (action, at = null, until = null) =>
  post("/api/transport", { action, at, until });

/** Upload browser files (picker or drop); the server imports them and reports each. */
export async function uploadFiles(files) {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  try {
    return await json("/api/upload", { method: "POST", body: form });
  } catch (error) {
    // A failed import still says why, file by file.
    if (error instanceof ApiError && error.body?.report)
      return { report: error.body.report, failed: error };
    throw error;
  }
}

/** A peak tile as a Float32Array of interleaved min/max (the browser caches it by ETag). */
export async function peakTile(media, level, tile) {
  const response = await request(`/api/peaks/${encodeURIComponent(media)}/${level}/${tile}`);
  return new Float32Array(await response.arrayBuffer());
}

export function liveUrl(location = globalThis.location) {
  return `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/live`;
}
