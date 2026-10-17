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
// The clipboard (WP46). Cut and paste are edits (edit() with clipboard_cut / clipboard_paste);
// copying changes no project, so it has its own route. Each answer carries `entries`.
export const getClipboard = () => json("/api/clipboard");
export const copyToClipboard = (body) => post("/api/clipboard/copy", body);
export const pinClipboardEntry = (id, pinned) =>
  post(`/api/clipboard/${encodeURIComponent(id)}/pin`, { pinned });
export const renameClipboardEntry = (id, name) =>
  post(`/api/clipboard/${encodeURIComponent(id)}/rename`, { name });
export const deleteClipboardEntry = (id) =>
  json(`/api/clipboard/${encodeURIComponent(id)}`, { method: "DELETE" });
export const undo = () => json("/api/undo", { method: "POST" });
export const redo = () => json("/api/redo", { method: "POST" });
export const transport = (action, at = null, until = null) =>
  post("/api/transport", { action, at, until });

/** Upload browser files (picker or drop); the server imports them and reports each. */
export const uploadFiles = (files) => {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  return importReport(() => json("/api/upload", { method: "POST", body: form }));
};

/** Link files in place by path (the desktop window's dialogs and drops): no upload. */
export const importPaths = (paths) =>
  importReport(() => post("/api/import", { paths, copy: false }));

async function importReport(send) {
  try {
    return await send();
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

export const getTransport = () => json("/api/transport");
