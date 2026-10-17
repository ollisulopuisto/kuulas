// The editor's entry point: wires the store, the API, the live channel, the
// canvases and the keyboard together. The decisions live in small pure modules
// (view.js, lanes.js, keys.js, ...); this file only applies their answers.
import * as api from "./api.js";
import { createEditor } from "./edits.js";
import { nextPanel } from "./focus.js";
import { followScroll } from "./follow.js";
import { frameToTime, RATE, xToFrame } from "./format.js";
import { formatNumber, initI18n, onLanguageChange, t } from "./i18n.js";
import { dragHasFiles, summariseImport } from "./importing.js";
import { createInspector } from "./inspector.js";
import { coreBindings, createKeymap, isTextField } from "./keys.js";
import { clampLaneHeight, projectEnd } from "./lanes.js";
import { connectLive } from "./live.js";
import { createOverview } from "./overview.js";
import { getState, reduceLive, serverPatch, setState, subscribe } from "./store.js";
import { createTimeline } from "./timeline.js";
import { createTrackHeaders } from "./tracks.js";
import { createTransport } from "./transport.js";
import * as View from "./view.js";

const $ = (id) => document.getElementById(id);
const WAVEFORM_GAIN = { min: 1 / 8, max: 32, snap: 0.04 };
const LANE_STEP = 8;
const SETTLE_MS = 160;
const NOTICE_MS = { error: 9000, ok: 4000 };
const GAIN_DIGITS = (value) => (Number.isInteger(value) ? 0 : 1);

// -- text -------------------------------------------------------------------

function translate() {
  for (const node of document.querySelectorAll("[data-i18n]"))
    node.textContent = t(node.dataset.i18n);
  for (const node of document.querySelectorAll("[data-i18n-title]"))
    node.title = t(node.dataset.i18nTitle);
  for (const node of document.querySelectorAll("[data-i18n-aria-label]")) {
    node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel));
  }
  document.title = t("ui.app.title");
}

let noticeTimer = null;
function showNotice(text, kind = "error") {
  const notice = $("notice");
  $("notice-text").textContent = text;
  notice.dataset.kind = kind;
  notice.hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => {
    notice.hidden = true;
  }, NOTICE_MS[kind]);
}
const showError = (error) => showNotice(error?.message || t("ui.error.title"));
$("notice-close").addEventListener("click", () => {
  $("notice").hidden = true;
});

// -- server state -----------------------------------------------------------

let fitWhole = true; // the view shows the whole edit and keeps doing so on resize/import
let views = View.initialViews();
let history = View.createViewHistory();
let settleTimer = null;
let wheelAnchor = 0;

const rate = () => getState().project?.rate ?? RATE;
const totalFrames = () => projectEnd(getState().project);
const width = () => Math.max(1, timeline?.size().width ?? 1);
const viewLevels = () =>
  View.zoomLevels({ width: width(), rate: rate(), totalFrames: totalFrames() });
const bounds = () => ({ width: width(), totalFrames: totalFrames() });

function apply(response) {
  setState(serverPatch(response, getState()));
  if (fitWhole) fitWholeEdit();
}

async function refresh() {
  apply(await api.getState());
}

const editor = createEditor({
  send: api.edit,
  getProject: () => getState().project,
  setProject: (project) => setState({ project }),
  acceptServer: apply,
  // The screen showed a result the server refused: go back to what it has.
  onError: (error) => {
    showError(error);
    void refresh().catch(showError);
  },
});

const transport = createTransport({
  post: api.transport,
  getState,
  setState,
  onError: showError,
});

// -- the view: zoom, scroll, Z, history ---------------------------------------

function setView({ zoom, scroll }, { record = true, whole = false } = {}) {
  const next = Math.max(View.SAMPLE_ZOOM, zoom);
  const at = View.clampScroll(scroll, next, width(), totalFrames());
  fitWhole = whole;
  setState({ zoom: next, scroll: at });
  views = View.rememberView(views, { zoom: next, scroll: at });
  if (record) history = View.visitView(history, { zoom: next, scroll: at });
}

function fitWholeEdit() {
  setView({ zoom: viewLevels()[0].zoom, scroll: 0 }, { record: false, whole: true });
}

function anchorFrame() {
  const state = getState();
  return View.pickAnchor({
    lastEdit: state.lastEditPoint,
    pointerFrame: timeline.pointerFrame(),
    playhead: state.playhead,
  }).frame;
}

function markPaused() {
  if (getState().playing) setState({ followPaused: true });
}

const actions = {
  togglePlay: () => void transport.toggle(),
  goHome() {
    const active = document.activeElement;
    if (isTextField(active)) active.blur();
    focusPanel("timeline");
  },
  cyclePanel: (direction) => focusPanel(nextPanel(getState().panel, direction)),
  zoomStep(direction) {
    const state = getState();
    const levels = viewLevels();
    const next = View.stepZoom(state.zoom, levels, direction);
    if (next === state.zoom) return;
    setView(View.zoomAt(state, anchorFrame(), next, bounds()), { whole: next === levels[0].zoom });
  },
  toggleView() {
    const state = getState();
    const levels = viewLevels();
    const result = View.toggleView(
      views,
      { zoom: state.zoom, scroll: state.scroll },
      {
        anchorFrame: anchorFrame(),
        width: width(),
        levels,
        totalFrames: totalFrames(),
      },
    );
    views = result.views;
    setView(result, { whole: result.views.current === "wide" && result.zoom === levels[0].zoom });
  },
  fitView() {
    const state = getState();
    if (!state.project) return;
    const target = View.fitTarget(state);
    if (target.end <= target.start) return;
    if (target.start === 0 && target.end === totalFrames()) fitWholeEdit();
    else setView(View.fitRange({ ...target, width: width() }));
    history = View.visitView(history, { zoom: getState().zoom, scroll: getState().scroll });
  },
  viewBack: () => stepHistory(View.backView),
  viewForward: () => stepHistory(View.forwardView),
};

function stepHistory(step) {
  const result = step(history);
  if (!result.view) return;
  history = result.history;
  setView(result.view, { record: false });
}

// Mod + wheel and pinch zoom continuously, then settle on a level when released
// within 8 % of one.
function settle() {
  const state = getState();
  const levels = viewLevels();
  const snapped = View.snapZoom(state.zoom, levels);
  if (snapped !== state.zoom) {
    setView(View.zoomAt(state, wheelAnchor, snapped, bounds()), {
      whole: snapped === levels[0].zoom,
    });
  } else {
    history = View.visitView(history, { zoom: state.zoom, scroll: state.scroll });
  }
}

function onWheel(intent, x) {
  const state = getState();
  if (intent.kind === "scroll") {
    if (intent.dx) {
      const scroll = View.clampScroll(
        state.scroll + intent.dx * state.zoom,
        state.zoom,
        width(),
        totalFrames(),
      );
      setState({ scroll });
      markPaused();
    }
    if (intent.dy) $("track-headers").scrollTop += intent.dy;
  } else if (intent.kind === "zoom") {
    const levels = viewLevels();
    const next = Math.min(levels[0].zoom, Math.max(View.SAMPLE_ZOOM, state.zoom * intent.factor));
    wheelAnchor = xToFrame(x, state.scroll, state.zoom);
    setView(View.zoomAt(state, wheelAnchor, next, bounds()), { record: false });
    clearTimeout(settleTimer);
    settleTimer = setTimeout(settle, SETTLE_MS);
  } else if (intent.kind === "waveform") {
    let gain = Math.min(
      WAVEFORM_GAIN.max,
      Math.max(WAVEFORM_GAIN.min, state.waveformGain * intent.factor),
    );
    if (Math.abs(gain - 1) < WAVEFORM_GAIN.snap) gain = 1;
    setState({ waveformGain: gain });
  }
}

// -- pointer on the timeline ------------------------------------------------------

function onPointerDown(hit, event) {
  const state = getState();
  if (hit.area === "ruler") {
    void transport.seek(hit.frame);
    return;
  }
  if (hit.area !== "lane" || !hit.row) return;
  const patch = { panel: "timeline" };
  if (hit.row.kind === "track") patch.focusTrack = hit.row.id;
  if (event.shiftKey && hit.clip) {
    const selection = new Set(state.selection);
    if (!selection.delete(hit.clip.id)) selection.add(hit.clip.id);
    setState({ ...patch, selection });
    return;
  }
  patch.selection = hit.clip ? new Set([hit.clip.id]) : new Set();
  setState(patch);
  void transport.seek(hit.frame);
}

// -- keyboard focus ------------------------------------------------------------------

const panelElements = {
  timeline: $("timeline"),
  transcript: $("panel-transcript"),
  inspector: $("panel-inspector"),
  history: $("panel-history"),
};

function focusPanel(name) {
  panelElements[name].focus();
  setState({ panel: name });
}

document.addEventListener("focusin", (event) => {
  const panel = event.target.closest?.("[data-panel]")?.dataset.panel;
  if (panel && panel !== getState().panel) setState({ panel });
});

const keymap = createKeymap();
for (const binding of coreBindings(actions)) keymap.bind(binding);
document.addEventListener("keydown", (event) => {
  if (!event.isComposing) keymap.handle(event);
});
// A focused button would otherwise also "click" on the key release.
document.addEventListener("keyup", (event) => {
  if (event.code === "Space" && !isTextField(event.target) && !event.metaKey && !event.ctrlKey) {
    event.preventDefault();
  }
});

// -- toolbar ------------------------------------------------------------------------------

$("play").addEventListener("click", () => actions.togglePlay());
$("undo").addEventListener("click", () => void api.undo().then(apply).catch(showError));
$("redo").addEventListener("click", () => void api.redo().then(apply).catch(showError));
$("zoom-in").addEventListener("click", () => actions.zoomStep(1));
$("zoom-out").addEventListener("click", () => actions.zoomStep(-1));
$("view-toggle").addEventListener("click", () => actions.toggleView());
$("fit").addEventListener("click", () => actions.fitView());
$("waveform-mode").addEventListener("change", (event) =>
  setState({ waveformMode: event.target.value }),
);
$("waveform-gain").addEventListener("click", () => setState({ waveformGain: 1 }));
$("lane-taller").addEventListener("click", () => setLaneHeight(LANE_STEP));
$("lane-shorter").addEventListener("click", () => setLaneHeight(-LANE_STEP));
$("follow").addEventListener("click", () => {
  const state = getState();
  if (state.followPaused) setState({ followPaused: false });
  else setState({ followMode: state.followMode === "page" ? "continuous" : "page" });
});
$("track-headers").addEventListener("scroll", (event) =>
  setState({ scrollY: event.target.scrollTop }),
);

function setLaneHeight(delta) {
  setState({ laneHeight: clampLaneHeight(getState().laneHeight + delta) });
}

// -- import: file picker and drag and drop ------------------------------------------------------

async function importFiles(files) {
  if (files.length === 0) return;
  try {
    const result = await api.uploadFiles(files);
    if (result.project) apply(result);
    const summary = summariseImport(result.report);
    const lines = [];
    if (summary.imported > 0) lines.push(t("ui.import.success", { count: summary.imported }));
    for (const failure of summary.failures) lines.push(t("ui.import.failed_file", failure));
    for (const warning of summary.warnings) lines.push(t("ui.import.warning", warning));
    if (lines.length === 0) lines.push(t("ui.import.failed"));
    showNotice(
      lines.join(" "),
      summary.failures.length === 0 && summary.imported > 0 ? "ok" : "error",
    );
  } catch (error) {
    showError(error);
  }
}

$("import").addEventListener("click", () => $("file-input").click());
$("file-input").addEventListener("change", (event) => {
  const files = [...event.target.files];
  event.target.value = "";
  void importFiles(files);
});

let dragDepth = 0;
const setDrop = (on) => {
  $("drop").hidden = !on;
};
window.addEventListener("dragenter", (event) => {
  if (!dragHasFiles(event.dataTransfer)) return;
  event.preventDefault();
  dragDepth += 1;
  setDrop(true);
});
window.addEventListener("dragover", (event) => {
  if (dragHasFiles(event.dataTransfer)) event.preventDefault();
});
window.addEventListener("dragleave", (event) => {
  if (!dragHasFiles(event.dataTransfer)) return;
  dragDepth = Math.max(0, dragDepth - 1);
  if (dragDepth === 0) setDrop(false);
});
window.addEventListener("drop", (event) => {
  if (!dragHasFiles(event.dataTransfer)) return;
  event.preventDefault();
  dragDepth = 0;
  setDrop(false);
  void importFiles([...event.dataTransfer.files]);
});

// -- the canvases and panels -----------------------------------------------------------------------

const trackHeaders = createTrackHeaders({
  root: $("track-headers"),
  editor,
  actions: { currentTrack: (id) => setState({ focusTrack: id }) },
});
const inspector = createInspector({ root: $("panel-inspector"), editor });

const timeline = createTimeline({
  stack: $("timeline-stack"),
  waveCanvas: $("wave"),
  overlayCanvas: $("timeline"),
  getState,
  actions: {
    pointerDown: onPointerDown,
    wheel: onWheel,
    resized() {
      if (fitWhole && getState().project) fitWholeEdit();
      overview?.redraw();
    },
  },
});
const overview = createOverview({
  canvas: $("overview"),
  getState,
  getTimelineWidth: width,
  actions: {
    scrollTo(scroll) {
      fitWhole = false;
      setState({ scroll: View.clampScroll(scroll, getState().zoom, width(), totalFrames()) });
      markPaused();
    },
  },
});

// -- render -----------------------------------------------------------------------------------------------

function spanText(state) {
  const info = View.describeZoom(state.zoom, viewLevels(), { width: width(), rate: rate() });
  if (info.kind === "whole") return t("ui.zoom.whole");
  if (info.kind === "samples") return t("ui.zoom.samples");
  const { unit, value } = View.spanParts(info.seconds);
  return t(`ui.zoom.${unit}`, { value: formatNumber(value, { digits: GAIN_DIGITS(value) }) });
}

function render(state, patch) {
  const changed = patch ? new Set(Object.keys(patch)) : null;
  const touched = (...names) => changed === null || names.some((name) => changed.has(name));
  timeline.redraw();
  if (
    touched(
      "project",
      "scroll",
      "zoom",
      "scrollY",
      "laneHeight",
      "waveformMode",
      "waveformScale",
      "waveformGain",
    )
  ) {
    timeline.redrawWaveforms();
  }
  if (touched("project", "scroll", "zoom")) overview.redraw();
  if (touched("playhead", "project")) {
    $("timecode").textContent = frameToTime(state.playhead, rate());
  }
  if (touched("playing")) {
    $("play-icon").textContent = state.playing ? "■" : "▶";
    $("play-label").textContent = t(state.playing ? "ui.transport.stop" : "ui.transport.play");
  }
  if (touched("zoom", "project", "scroll")) {
    const view = t(views.current === "close" ? "ui.view.close" : "ui.view.wide");
    $("zoom-chip").textContent = t("ui.zoom.label", { view, span: spanText(state) });
    $("view-toggle").textContent = view;
    $("view-toggle").setAttribute("aria-pressed", String(views.current === "close"));
  }
  if (touched("live")) {
    const chip = $("live-chip");
    chip.hidden = state.live === "open";
    chip.textContent = t(
      state.live === "reconnecting" ? "ui.live.reconnecting" : "ui.live.connecting",
    );
    chip.title = state.live === "reconnecting" ? t("ui.live.reconnecting_title") : "";
  }
  if (touched("canUndo", "canRedo")) {
    $("undo").disabled = !state.canUndo;
    $("redo").disabled = !state.canRedo;
  }
  if (touched("waveformGain")) {
    const button = $("waveform-gain");
    button.hidden = state.waveformGain === 1;
    const value = formatNumber(state.waveformGain, { digits: state.waveformGain < 10 ? 1 : 0 });
    button.textContent = `×${value}`;
    button.title = t("ui.view.waveform_reset", { value });
  }
  if (touched("followMode", "followPaused")) {
    $("follow").textContent = t(
      state.followMode === "page" ? "ui.view.follow_page" : "ui.view.follow_continuous",
    );
    $("follow").setAttribute("aria-pressed", String(state.followPaused));
  }
  if (touched("waveformMode")) $("waveform-mode").value = state.waveformMode;
  if (touched("project", "focusTrack", "laneHeight")) trackHeaders.update(state);
  if (touched("project", "selection")) inspector.update(state);
  if (touched("project")) {
    const empty = $("empty");
    const hasClips = state.project?.tracks.some((track) => track.clips.length > 0);
    empty.hidden = !state.project || hasClips;
    empty.textContent = t("ui.project.empty");
  }
  if (touched("panel")) {
    for (const node of document.querySelectorAll("[data-panel]")) {
      node.toggleAttribute("data-focused", node.dataset.panel === state.panel);
    }
  }
  if (touched("playhead", "playing", "zoom", "scroll", "followMode", "followPaused")) follow(state);
}

// While playing, keep the playhead in view (page or continuous) unless the user
// scrolled away by hand.
function follow(state) {
  const next = followScroll({
    mode: state.followMode,
    paused: state.followPaused,
    playing: state.playing,
    playhead: state.playhead,
    scroll: state.scroll,
    zoom: state.zoom,
    width: width(),
  });
  if (next.scroll !== state.scroll || next.paused !== state.followPaused) {
    setState({ scroll: next.scroll, followPaused: next.paused });
  }
}

subscribe(render);
onLanguageChange(() => {
  translate();
  render(getState(), null);
});

// -- start --------------------------------------------------------------------------------------------------

try {
  await initI18n({ document });
} catch (error) {
  console.error("the translations could not be loaded; showing message keys", error);
}
translate();
render(getState(), null);

try {
  const [state, words] = await Promise.all([api.getState(), api.getWords()]);
  apply(state);
  setState({ words: words.words ?? [] });
} catch (error) {
  showError(error);
}

let handledNotice = 0;
let wasDown = false;
connectLive({
  url: api.liveUrl(),
  onStatus(status) {
    setState({ live: status });
    if (status === "open" && wasDown) {
      // Whatever happened while the connection was gone: fetch it again.
      void refresh().catch(showError);
      void api
        .getTransport()
        .then((s) => setState({ playing: s.playing, playhead: s.position }))
        .catch(showError);
    }
    wasDown = status === "reconnecting";
  },
  onMessage(message) {
    const result = reduceLive(getState(), message);
    if (Object.keys(result.patch).length > 0) setState(result.patch);
    // An answer to our own edit arrives as a state_changed too; while edits are
    // still going out, the editor shows the newest value and applies the last answer.
    if (result.refresh && !editor.busy) void refresh().catch(showError);
    if (result.notice && result.notice.id > handledNotice) {
      handledNotice = result.notice.id;
      showNotice(result.notice.text);
    }
  },
});

// The long-task monitor of the performance rule (no main-thread task over 16 ms):
// open the page with ?dev to log every task that breaks it.
if (new URLSearchParams(location.search).has("dev") && "PerformanceObserver" in window) {
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries())
        console.warn("long task", Math.round(entry.duration), "ms", entry);
    }).observe({ type: "longtask", buffered: true });
  } catch {
    console.warn("long-task monitoring is not supported in this browser");
  }
}
