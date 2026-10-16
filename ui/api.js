async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw Object.assign(new Error(body.error?.text ?? response.statusText), { body, status: response.status });
  }
  return response;
}

async function json(path, options) {
  return (await request(path, options)).json();
}

export const getState = () => json("/api/state");
export const getWords = () => json("/api/words");
export const edit = (op, args, label = null, coalesce = null) =>
  json("/api/edit", { method: "POST", body: JSON.stringify({ op, args, label, coalesce }) });
export const command = (name, args = {}) =>
  json("/api/command", { method: "POST", body: JSON.stringify({ name, args }) });
export const transport = (action, at = null, until = null) =>
  json("/api/transport", { method: "POST", body: JSON.stringify({ action, at, until }) });
export const undo = () => json("/api/undo", { method: "POST" });
export const redo = () => json("/api/redo", { method: "POST" });
export const importPaths = (paths, copy = false) =>
  json("/api/import", { method: "POST", body: JSON.stringify({ paths, copy }) });
export async function uploadFiles(files) {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  return json("/api/upload", { method: "POST", body: form, headers: {} });
}

const peakCache = new Map();
export async function peakTile(media, level, tile = 0) {
  const key = `${media}/${level}/${tile}`;
  if (!peakCache.has(key)) {
    peakCache.set(key, request(`/api/peaks/${encodeURIComponent(media)}/${level}/${tile}`)
      .then((response) => response.arrayBuffer()));
  }
  try {
    return await peakCache.get(key);
  } catch (error) {
    peakCache.delete(key);
    throw error;
  }
}

export function connectLive(onMessage, onStatus = () => {}) {
  let socket;
  let stopped = false;
  let retry;
  const connect = () => {
    if (stopped) return;
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${location.host}/api/live`);
    socket.addEventListener("open", () => onStatus(true));
    socket.addEventListener("message", (event) => {
      try { onMessage(JSON.parse(event.data)); } catch { /* Ignore malformed pushes. */ }
    });
    socket.addEventListener("close", () => {
      onStatus(false);
      if (!stopped) retry = setTimeout(connect, 1000);
    });
    socket.addEventListener("error", () => socket.close());
  };
  connect();
  return () => { stopped = true; clearTimeout(retry); socket?.close(); };
}
