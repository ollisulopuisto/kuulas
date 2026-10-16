import * as api from "./api.js";
import { createTimeline } from "./timeline.js";
import { RATE, frameToTime, zoomAround } from "./format.js";
import { initI18n, onLanguageChange, setLanguageNow, t } from "./i18n.js";
import { getState, setState, subscribe } from "./store.js";
import { renderInspector } from "./inspector.js";
import { renderTracks } from "./tracks.js";

const element = (id) => document.getElementById(id);
const canvas = element("timeline");
let timeline;
let lastProject;
let previousKey;

function translate() {
  for (const node of document.querySelectorAll("[data-i18n]")) node.textContent = t(node.dataset.i18n);
  for (const node of document.querySelectorAll("[data-i18n-title]")) node.title = t(node.dataset.i18nTitle);
}

function showError(error) {
  const notice = element("notice");
  notice.textContent = error?.message || t("ui.error.title");
  notice.hidden = false;
  clearTimeout(showError.timer);
  showError.timer = setTimeout(() => { notice.hidden = true; }, 7000);
}

function acceptServerState(response) {
  const patch = {};
  for (const key of ["project", "head", "can_undo", "can_redo"]) {
    if (key in response) patch[{ can_undo: "canUndo", can_redo: "canRedo" }[key] ?? key] = response[key];
  }
  setState(patch);
}

async function refresh() {
  acceptServerState(await api.getState());
}

function render(state) {
  timeline?.draw();
  element("timecode").textContent = frameToTime(state.playhead, state.language);
  element("play").textContent = t(state.playing ? "ui.transport.stop" : "ui.transport.play");
  element("play").setAttribute("aria-label", element("play").textContent);
  const key = `${state.head}/${state.selection.size}/${[...state.selection].join()}`;
  if (state.project !== lastProject || key !== previousKey) {
    if (state.project !== lastProject) {
      renderTracks(element("track-headers"), state.project, refresh);
      lastProject = state.project;
    }
    renderInspector(element("inspector-panel"), state, refresh);
    previousKey = key;
  }
  element("undo").disabled = !state.canUndo;
  element("redo").disabled = !state.canRedo;
  const seconds = state.zoom / (state.project?.rate ?? RATE);
  element("zoom-label").textContent = t("ui.zoom.label", { seconds: seconds < 1 ? `${Math.round(seconds * 1000)} ms` : `${Number(seconds.toPrecision(2))} s` });
  const empty = element("transcript-content");
  if (!state.project?.tracks.some((track) => track.clips.length)) empty.textContent = t("ui.project.empty");
}

async function setTransport(action, at = null) {
  try {
    const status = await api.transport(action, at);
    setState({ playing: status.playing, playhead: status.position });
  } catch (error) { showError(error); }
}

element("play").addEventListener("click", () => void setTransport(getState().playing ? "stop" : "play", getState().playhead));
element("stop").addEventListener("click", () => void setTransport("stop"));
element("undo").addEventListener("click", () => void api.undo().then(acceptServerState).catch(showError));
element("redo").addEventListener("click", () => void api.redo().then(acceptServerState).catch(showError));
element("import").addEventListener("click", () => element("file-input").click());
element("file-input").addEventListener("change", async (event) => {
  const files = [...event.target.files];
  if (!files.length) return;
  try {
    const result = await api.uploadFiles(files);
    acceptServerState(result);
    if (result.report?.some((item) => !item.ok)) showError(new Error(result.report.find((item) => !item.ok).error?.text ?? t("ui.import.failed")));
  } catch (error) { showError(error); }
  event.target.value = "";
});

element("zoom-in").addEventListener("click", () => {
  const state = getState();
  setState(zoomAround({ ...state, x: canvas.clientWidth / 2, nextZoom: Math.max(1, state.zoom / 2) }));
});
element("zoom-out").addEventListener("click", () => {
  const state = getState();
  setState(zoomAround({ ...state, x: canvas.clientWidth / 2, nextZoom: state.zoom * 2 }));
});
element("fit").addEventListener("click", () => {
  const state = getState();
  const end = state.project?.tracks.flatMap((track) => track.clips).reduce((max, clip) => Math.max(max, clip.end), 0) ?? 0;
  if (end) setState({ zoom: end / Math.max(1, canvas.clientWidth), scroll: 0 });
});
element("waveform-mode").addEventListener("change", (event) => setState({ waveformMode: event.target.value }));

canvas.addEventListener("dblclick", (event) => {
  const rect = canvas.getBoundingClientRect();
  setState({ playhead: Math.max(0, Math.round(getState().scroll + (event.clientX - rect.left) * getState().zoom)) });
  void setTransport("seek", getState().playhead);
});

document.addEventListener("keydown", (event) => {
  const focusedInput = event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement || event.target instanceof HTMLTextAreaElement;
  if (event.key === "Escape") { canvas.focus(); return; }
  if (event.key === "F6") {
    event.preventDefault();
    const panels = [canvas, element("transcript-panel"), element("inspector-panel"), element("history-panel")];
    const index = panels.indexOf(document.activeElement);
    panels[(index + (event.shiftKey ? panels.length - 1 : 1)) % panels.length].focus();
    return;
  }
  if (focusedInput) return;
  if (event.code === "Space") { event.preventDefault(); void setTransport(getState().playing ? "stop" : "play", getState().playhead); }
  else if (event.key === "=" || event.key === "+") element("zoom-in").click();
  else if (event.key === "-") element("zoom-out").click();
  else if (event.key.toLowerCase() === "z" && !event.altKey && !event.shiftKey) {
    const state = getState();
    const next = state.closeZoom ?? state.zoom;
    setState({ zoom: state.zoom === next ? state.wideZoom ?? Math.max(state.zoom * 10, RATE * 30) : next, closeZoom: state.zoom === next ? next : state.closeZoom, wideZoom: state.zoom === next ? state.wideZoom ?? Math.max(state.zoom * 10, RATE * 30) : state.wideZoom });
  }
});

subscribe(render);
onLanguageChange(translate);
await initI18n({ document });
translate();
timeline = createTimeline(canvas, getState, setState);
try {
  const [state, wordResult] = await Promise.all([api.getState(), api.getWords()]);
  acceptServerState(state);
  setState({ words: wordResult.words ?? [] });
} catch (error) { showError(error); }
api.connectLive((message) => {
  if (message.type === "position") setState({ playing: message.playing, playhead: message.position });
  else if (message.type === "state_changed" && message.head !== getState().head) void refresh().catch(showError);
  else if (message.type === "notice") showError(new Error(message.text));
});
