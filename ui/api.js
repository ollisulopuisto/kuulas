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
/** This project's remembered view (kept outside the project): { view: object | null }. */
export const getBuild = () => json("/api/build");
/** View > Language: { setting: "auto" | "en" | "fi", language } (the server's own view). */
export const getLanguage = () => json("/api/language");
export const putLanguage = (setting) =>
  json("/api/language", { method: "PUT", body: JSON.stringify({ setting }) });
/** Help > Log level: { level, setting, levels, from_environment }. */
export const getLogLevel = () => json("/api/log-level");
export const putLogLevel = (level) => post("/api/log-level", { level });
/** Help > Record a performance report: { state: idle | running | done | failed, seconds,
 * elapsed, samples, report (the file, relative to home), error }. */
export const getProfile = () => json("/api/profile");
export const startProfile = (seconds) => post("/api/profile", { action: "start", seconds });
export const stopProfile = () => post("/api/profile", { action: "stop" });
export const getViewMemory = () => json("/api/view-memory");
/** `keepalive` lets the write finish while the page is being left. */
export const putViewMemory = (view, { now = false } = {}) =>
  json(`/api/view-memory${now ? "?now=true" : ""}`, {
    method: "PUT",
    body: JSON.stringify({ view }),
    keepalive: true,
  });
export const getWords = () => json("/api/words");
// Recording (WP12a): the recorder is its own program; the server is its viewer and remote.
/** { available, recording, ours, take, position_frames, disk, notices, pending, ... } */
export const getRecordStatus = (channels = 1) =>
  json(`/api/record/status?channels=${Math.max(1, Math.round(Number(channels)) || 1)}`);
/** { devices: [{ index, name, channels, default }] } (starts the recorder if need be). */
export const getRecordDevices = () => json("/api/record/devices");
/** { device: {index, name} | null, channels: [{channel, track_id (null: new track), name}], at } */
export const startRecording = (body) => post("/api/record/start", body);
/** Pre-roll (WP12c): listen to the input, keeping the last seconds in memory only, nothing on
 * disk. { device, channels: [numbers], preroll_s }. Repeated, it keeps the recorder armed. */
export const armRecording = (body) => post("/api/record/arm", body);
/** Stop listening and drop the buffer. */
export const disarmRecording = () => post("/api/record/disarm", {});
/** { mode: "two_step" | "one_click" | "hold", held_ms }: the server refuses a stop without one. */
export const stopRecording = (body) => post("/api/record/stop", body);
/** Put takes left by a crash on the timeline: the state, plus { imported, pending }. */
export const importTakes = (takes) => post("/api/record/import", { takes });
/** The session's statistics (WP70): { stats, groups: [{ title, rows: [[label, value]] }], text }. */
export const getStats = () => json("/api/stats");
/** File > Locate media… (WP39): { missing: [{ id, name, size }], partial: [{ id, name, can_complete }] }. */
export const getMediaStatus = () => json("/api/media/status");
/** Look under a folder by SHA-256: { found: [{ id, name, path }], still_missing, partial }. */
export const locateMedia = (folder) => post("/api/media/locate", { folder });
/** File > Send a copy… (WP32): what each choice would carry: { none, used, all: { bytes, ... }, offline }. */
export const getSendCopyPlan = () => json("/api/send-copy/plan");
/** Write the copy: { path, copy, media, carried, relink, unavailable, bytes }. */
export const sendCopy = (body) => post("/api/send-copy", body);
/** Short-term loudness per track and for the mix, with each track's integrated LUFS and target
 * (WP49). Takes seconds on a long programme: always asked in the background; `signal` cancels. */
export const getLoudnessCurve = (signal) => json("/api/loudness-curve", { signal });
/** The frames Tab stops at in one mode (edges, transients, words): { points: [frame] }. */
export const getEditPoints = (mode, track = null) =>
  json(`/api/edit-points?mode=${mode}${track ? `&track=${encodeURIComponent(track)}` : ""}`);
/** What cutting these words (refs: { track, clip, index }) would also remove from other tracks. */
export const cutPreview = (words) => post("/api/cut-preview", { words });
/** Correct one word's text (a new transcript revision, one undo step). */
export const correctWord = (media, index, w) =>
  json("/api/word", { method: "PUT", body: JSON.stringify({ media, index, w }) });
/**
 * Queue transcription of these media; answers { jobs: [job id] }. `backend` "local" (one job per
 * recording; `force`: also music-only recordings, which the server refuses) or "colab" (ONE job, the audio is uploaded to Google: ask first, see app.js).
 */
export const transcribe = (mediaIds, { backend = "local", model, language, force = false } = {}) =>
  post("/api/transcribe", { media_ids: mediaIds, backend, model, language, force });
/** The Colab transcription command: { settings (as stored), resolved (defaults filled in) }. */
export const colabSettings = () => json("/api/settings/colab");
export const saveColabSettings = (settings) =>
  json("/api/settings/colab", { method: "PUT", body: JSON.stringify(settings) });
/** Is Colab signed in to Google, and how is a sign-in going: { signed_in, state, url, lines, error }. */
export const colabSignin = () => json("/api/colab/signin");
/** Start the Google sign-in (opens the browser; answers the same status). */
export const startColabSignin = () => post("/api/colab/signin", {});
/** Give the code Google shows to the waiting sign-in. The code is not kept. */
export const sendColabCode = (code) => post("/api/colab/signin/code", { code });
export const cancelColabSignin = () => json("/api/colab/signin", { method: "DELETE" });
export const getJobs = () => json("/api/jobs");
/** What the background transcription jobs did since the last call, told once:
 * { notices: [{ kind: "ok" | "error", text, job }] } (WP79). */
export const jobNotices = () => json("/api/jobs/notices");
/** Start every interrupted background transcription again: { restarted: [job id] }. */
export const restartInterrupted = () => post("/api/jobs/restart-interrupted", {});
/** One edit: the whole project comes back. `coalesce` merges a drag into one undo step. */
export const edit = ({ op, args, label = null, coalesce = null }) =>
  post("/api/edit", { op, args, label, coalesce });
/** A file the server offers for download: { blob, disposition } (Content-Disposition). */
export async function download(path) {
  const response = await request(path);
  return { blob: await response.blob(), disposition: response.headers.get("Content-Disposition") };
}
/** Queue the one job that renders every region to its own file; answers { jobs: [job id] }. */
export const exportRegions = (options = {}) => post("/api/export-regions", options);
/** Queue the export of every track (`options.format`: a format id, default WAV); answers
 * { jobs: [job id] }. */
export const exportTracks = (options = {}) => post("/api/export-tracks", options);
/** Queue the export of the mix as one file (`options.format`); answers { jobs: [job id] }. */
/** Queue the mix with the automixer (WP68): { target_lufs, ad_spot?, ad_duration? }; answers
 * { jobs: [job id] }. */
/** What Auto-Silence with these options would close, per track; changes nothing. Answers
 * { jobs: [job id] }; the finished job's `result` is { tracks: [{ name, close_s, stretches, now_s }] }. */
export const autoSilencePreview = (options = {}) => post("/api/auto-silence/preview", options);
/** Set music level: a job that measures the speech and the music beds; changes nothing. */
export const musicLevelMeasure = (options = {}) => post("/api/music-level/measure", options);
export const automix = (options = {}) => post("/api/automix", options);
/** The automixer command: { settings (as stored), resolved (defaults filled in) }. */
export const automixerSettings = () => json("/api/settings/automixer");
/** The installed audio plug-ins: { plugins: [{ name, format, path }] } (scanned once;
 * `refresh` scans again). */
export const plugins = (refresh = false) => json(`/api/plugins${refresh ? "?refresh=1" : ""}`);
export const saveAutomixerSettings = (settings) =>
  json("/api/settings/automixer", { method: "PUT", body: JSON.stringify(settings) });
/** What the export dialog starts from: { mix, tracks (the last settings or null), folder,
 * remembered, edit, project (the project's path) }. */
export const exportSettings = () => json("/api/export-settings");
export const exportFolder = () => json("/api/export-folder");
/** File > New project… in a plain browser: make `<parent>/<name>.kuulas` and open it in a new
 * tab; answers { path }. */
export const newProject = (body) => post("/api/project/new", body);
/** File > Open project… in a plain browser: open the project at `body.path` in a new tab. */
export const openProject = (body) => post("/api/project/open", body);
export const exportMix = (options = {}) => post("/api/export-mix", options);
/** The formats the server can write: [{ id, label, ext, lossless }], WAV first. */
export const exportFormats = () => json("/api/export-formats");
export const cancelJob = (id) => json(`/api/jobs/${encodeURIComponent(id)}`, { method: "DELETE" });
export const command = (name, args = {}) => post("/api/command", { name, args });
// Cut candidates (WP18). Deciding, applying and marking are commands (one undo step each);
// the list and the preview data only read. `state`: "open" | "cut" | "kept" or null for all.
export const getCandidates = (state = null) =>
  json(`/api/candidates${state ? `?state=${encodeURIComponent(state)}` : ""}`);
export const getCandidatePreview = (id, mode = "soft") =>
  json(`/api/candidates/${encodeURIComponent(id)}/preview?mode=${encodeURIComponent(mode)}`);
// The clipboard (WP46). Cut and paste are edits (edit() with clipboard_cut / clipboard_paste);
// copying changes no project, so it has its own route. Each answer carries `entries`.
export const getClipboard = () => json("/api/clipboard");
export const copyToClipboard = (body) => post("/api/clipboard/copy", body);
export const previewClipboardEntry = (id, limit = true) =>
  post(`/api/clipboard/${encodeURIComponent(id)}/preview`, { limit });
export const pinClipboardEntry = (id, pinned) =>
  post(`/api/clipboard/${encodeURIComponent(id)}/pin`, { pinned });
export const renameClipboardEntry = (id, name) =>
  post(`/api/clipboard/${encodeURIComponent(id)}/rename`, { name });
export const deleteClipboardEntry = (id) =>
  json(`/api/clipboard/${encodeURIComponent(id)}`, { method: "DELETE" });
/** The shared store: { entries }. Marking is post(.../share): { entries, shared }. */
export const getClipboardShared = () => json("/api/clipboard/shared");
export const shareClipboardEntry = (id, shared) =>
  post(`/api/clipboard/${encodeURIComponent(id)}/share`, { shared });
/** The recent projects ({ projects }) and one project's clipboard, read-only ({ project, entries }). */
export const getClipboardProjects = () => json("/api/clipboard/projects");
export const getClipboardProject = (path) =>
  json(`/api/clipboard/project?path=${encodeURIComponent(path)}`);
/** Copy an entry of the shared store or another project into this project: { entry, entries }. */
export const adoptClipboardEntry = (entry, fromProject = "") =>
  post("/api/clipboard/adopt", { entry, from_project: fromProject });
/** Drop this project's oldest entries, keeping the newest `keep`: { removed, entries }. */
export const clearOldClipboard = (keep) => post("/api/clipboard/clear-old", { keep });
/** A page of steps, newest first: { nodes, head, more, can_undo, can_redo }. */
export const getHistory = ({ limit = 100, before = null } = {}) =>
  json(`/api/history?limit=${limit}${before ? `&before=${encodeURIComponent(before)}` : ""}`);
/** Add a step equal to an older one (nothing is lost); answers like undo, plus `context`. */
export const restore = (node) => post("/api/restore", { node });
export const undo = () => json("/api/undo", { method: "POST" });
export const redo = () => json("/api/redo", { method: "POST" });
/**
 * `skip` (play only): frame ranges [a, b) the engine jumps over, crossfaded.
 * `options` (play only): { speed, preserve_pitch }, the tape speed (negative is backward).
 */
export const transport = (action, at = null, until = null, skip = null, options = null) =>
  post("/api/transport", {
    action,
    at,
    until,
    ...(skip === null ? {} : { skip }),
    ...(options ?? {}),
  });

/**
 * Upload browser files (picker or drop); the server imports them and reports each.
 * `options`: mode, order, track_naming, start_frame (the placement; see import_plan.py).
 */
export const uploadFiles = (files, options = {}) => {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  for (const [key, value] of Object.entries(options)) form.append(key, String(value));
  return importReport(() => json("/api/upload", { method: "POST", body: form }));
};

/** A browser's take for a narration placeholder (WP43): uploaded and put in its place. */
export const uploadTake = (placeholderId, file) => {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("placeholder_id", placeholderId);
  return json("/api/placeholder-take", { method: "POST", body: form });
};

/** Link files in place by path (the desktop window's dialogs and drops): no upload. */
export const importPaths = (paths, options = {}) =>
  importReport(() => post("/api/import", { paths, copy: false, ...options }));

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

/** Every drifting or free clip with its offset in frames: what the timeline's badges draw (R51). */
export const getSync = () => json("/api/sync");
/** What a moving sync command (resync, resync_from, send_home) would do; changes nothing. */
export const syncPreview = (name, args = {}) => post("/api/sync/preview", { name, args });
/** The history step that put a clip out of sync: { cause: { label, op, track_id, created } | null }. */
export const getSyncCause = (clipId) => json(`/api/sync-cause/${encodeURIComponent(clipId)}`);

/** Where a recording is used in the edit (the inspector's Source section); `signal` cancels. */
export const getSourceMap = (sha256, signal) =>
  json(`/api/source-map?media=${encodeURIComponent(sha256)}`, { signal });
