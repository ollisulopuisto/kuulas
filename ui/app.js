// The editor's entry point: wires the store, the API, the live channel, the
// canvases and the keyboard together. The decisions live in small pure modules
// (view.js, lanes.js, keys.js, ...); this file only applies their answers.
import * as api from "./api.js";
import { createClipboardPanel } from "./clipboard-panel.js";
import { createEditor } from "./edits.js";
import { nextPanel } from "./focus.js";
import { followScroll } from "./follow.js";
import { frameToTime, RATE, xToFrame } from "./format.js";
import { GATE_OPEN_COMMAND, openStretchEdit, stretchAt } from "./gate.js";
import { HELP_COMMAND, shortcutsFor } from "./help.js";
import { createHelpPanel } from "./help-panel.js";
import { undoNotice } from "./history-model.js";
import { createHistoryPanel } from "./history-panel.js";
import { formatNumber, formatShortcut, initI18n, onLanguageChange, t } from "./i18n.js";
import { collectDroppedFiles, importOptionsFor } from "./import-drop.js";
import { createImportPanel, panelModel } from "./import-panel.js";
import { dragHasFiles, nativeBridge, summariseImport } from "./importing.js";
import { createInspector } from "./inspector.js";
import { formatCombo } from "./keymap-config.js";
import { detectPlatform, isTextField } from "./keys.js";
import { clampLaneHeight, pointerIntent, projectEnd } from "./lanes.js";
import { connectLive } from "./live.js";
import { motionMode } from "./motion.js";
import { createOverview } from "./overview.js";
import { setupKeyboard } from "./shell-keys.js";
import { getState, reduceLive, serverPatch, setState, subscribe } from "./store.js";
import { densityAttribute, nextTheme, themeAttribute } from "./theme.js";
import { createTimeline } from "./timeline.js";
import { createTrackHeaders } from "./tracks.js";
import { createTranscript } from "./transcript.js";
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
  for (const node of document.querySelectorAll("[data-shortcut]"))
    node.textContent = formatShortcut(node.dataset.shortcut);
  document.title = t("ui.app.title");
}

let noticeTimer = null;
// `undo`: the message offers an Undo button (the edit keys' toast).
function showNotice(text, kind = "error", { undo = false } = {}) {
  const notice = $("notice");
  $("notice-text").textContent = text;
  $("notice-undo").hidden = !undo;
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
$("notice-undo").addEventListener("click", () => {
  $("notice").hidden = true;
  $("undo").click();
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

// -- the gate (WP44) ------------------------------------------------------------------

// "Open this stretch": one remove_gate_range edit, one undo step. `gate` is a
// hit ({ trackId, range }); without one, the closed stretch under the play
// cursor on the current track. The keymap binds GATE_OPEN_COMMAND to this.
function openGateStretch(gate) {
  const state = getState();
  const target = gate ?? stretchAt(state.project, state.focusTrack, state.playhead, state.zoom);
  if (!target) return;
  editor.change({
    ...openStretchEdit(target.trackId, target.range),
    label: t("ui.gate.open_stretch"),
  });
}
// Command registry for the keyboard layer: id -> function.
export const commands = { [GATE_OPEN_COMMAND]: () => openGateStretch() };

// -- pointer on the timeline ------------------------------------------------------

function onPointerDown(hit, event) {
  // The click rule lives in lanes.js pointerIntent (tested): anywhere in the
  // lane area sets the play cursor, a clip is also selected, Shift only toggles.
  const intent = pointerIntent(hit, { shift: event.shiftKey });
  if (!intent) return;
  const state = getState();
  const patch = { panel: "timeline" };
  if (hit.row?.kind === "track" && !event.shiftKey) {
    patch.focusTrack = hit.row.id;
    patch.focusBus = null;
  } else if (hit.row?.kind === "bus" && !event.shiftKey) patch.focusBus = hit.row.id;
  if (intent.selection === "replace") patch.selection = new Set([intent.clip.id]);
  else if (intent.selection === "clear") patch.selection = new Set();
  else if (intent.selection === "toggle") {
    const selection = new Set(state.selection);
    if (!selection.delete(intent.clip.id)) selection.add(intent.clip.id);
    patch.selection = selection;
  }
  setState(patch);
  if (intent.seek !== null) void transport.seek(intent.seek);
}

// -- keyboard focus ------------------------------------------------------------------

const panelElements = {
  timeline: $("timeline"),
  transcript: $("panel-transcript"),
  inspector: $("panel-inspector"),
  clipboard: $("panel-clipboard"),
  history: $("panel-history"),
};
const SIDEBAR_TABS = ["inspector", "clipboard", "history"];

function focusPanel(name) {
  // A sidebar tab that is not showing must show before it can take the focus.
  if (SIDEBAR_TABS.includes(name)) setState({ sidebarTab: name });
  panelElements[name].focus();
  setState({ panel: name });
}

document.addEventListener("focusin", (event) => {
  const panel = event.target.closest?.("[data-panel]")?.dataset.panel;
  if (panel && panel !== getState().panel) setState({ panel });
});

for (const tab of document.querySelectorAll(".side-tab")) {
  tab.addEventListener("click", () => focusPanel(tab.dataset.tab));
  tab.addEventListener("keydown", (event) => {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    if (!step) return;
    event.preventDefault();
    const next =
      SIDEBAR_TABS[
        (SIDEBAR_TABS.indexOf(tab.dataset.tab) + step + SIDEBAR_TABS.length) % SIDEBAR_TABS.length
      ];
    setState({ sidebarTab: next });
    $(`tab-${next}`).focus();
  });
}

// The transcript dock (WP7): paragraphs per speaker turn, following the playback.
const transcript = createTranscript({
  root: $("panel-transcript"),
  getState,
  setState,
  api,
  actions: {
    seek: (frame) => void transport.seek(frame),
    showError,
    applyResponse: apply,
    run: (id) => keyboard.registry.run(id, null, getState()),
  },
});

// The whole keyboard layer: keymap, palette, cheat sheet, menu bar, hints (shell-keys.js).
const keyboard = setupKeyboard({
  actions,
  t,
  notify: showNotice,
  onLanguageChange,
  // The Help button shows the key help has now, F1 or the user's own.
  onRefresh(entries) {
    const button = $("help-button");
    const platform = detectPlatform();
    const keys = shortcutsFor(HELP_COMMAND, entries);
    const aria = (combo) => combo.replace(/\bMod\b/, platform === "mac" ? "Meta" : "Control");
    button.setAttribute("aria-keyshortcuts", keys.map(aria).join(" "));
    button.title = keys.map((combo) => formatCombo(combo, platform)).join(" ");
  },
  app: {
    getState,
    patch: setState,
    openHelp: () => void help.open(),
    undo: () => $("undo").click(),
    redo: () => $("redo").click(),
    restoreStep: () => restoreStep(getState().historySelected),
    openHistory: () => focusPanel("history"),
    edit: (change) => editor.change(change),
    toast: (text, options) => showNotice(text, "ok", options),
    copy: (body) => copyToClipboard(body),
    refreshClipboard: () => void refreshClipboard(),
    now: () => performance.now(),
    chooseMedia: () => chooseMedia(),
    // The transcript's X: cut the words' stretch on every track.
    cutWords: (indices) =>
      api
        .command("cut_words", { indices })
        .then((response) => {
          apply(response);
          return true;
        })
        .catch((error) => {
          showError(error);
          return false;
        }),
    correct: () => transcript.startCorrect(),
    focusName: () => inspector.focusName(),
    openGateStretch: () => openGateStretch(),
    seek: (frame) => void transport.seek(frame),
    totalFrames,
  },
});
// A focused button would otherwise also "click" on the key release.
document.addEventListener("keyup", (event) => {
  if (event.code === "Space" && !isTextField(event.target) && !event.metaKey && !event.ctrlKey) {
    event.preventDefault();
  }
});

// -- toolbar ------------------------------------------------------------------------------

$("play").addEventListener("click", () => actions.togglePlay());
// Undo and redo say so when they pass a session marker: "Undid a step from yesterday: ...".
const moveHistory = (call) => () =>
  void call()
    .then((response) => {
      apply(response);
      const notice = undoNotice(response.moved, Date.now(), t);
      if (notice) showNotice(notice, "ok");
    })
    .catch(showError);
$("undo").addEventListener("click", moveHistory(api.undo));
$("redo").addEventListener("click", moveHistory(api.redo));
$("zoom-in").addEventListener("click", () => actions.zoomStep(1));
$("zoom-out").addEventListener("click", () => actions.zoomStep(-1));
$("view-toggle").addEventListener("click", () => actions.toggleView());
$("fit").addEventListener("click", () => actions.fitView());
$("waveform-mode").addEventListener("change", (event) =>
  setState({ waveformMode: event.target.value }),
);
$("waveform-gain").addEventListener("click", () => setState({ waveformGain: 1 }));
$("group-chip").addEventListener("click", () => setState({ groupEditing: true }));
$("lane-taller").addEventListener("click", () => setLaneHeight(LANE_STEP));
$("lane-shorter").addEventListener("click", () => setLaneHeight(-LANE_STEP));
$("follow").addEventListener("click", () => {
  const state = getState();
  if (state.followPaused) setState({ followPaused: false });
  else setState({ followMode: state.followMode === "page" ? "continuous" : "page" });
});
// The theme: follow the OS unless the user picked light or dark. A per-viewer
// convenience until remembered settings (WP35) own it; storage may be blocked.
const THEME_KEY = "kuulas.theme";
let themeChoice = "system";
try {
  themeChoice = localStorage.getItem(THEME_KEY) ?? "system";
} catch {
  // Private mode or blocked storage: the OS decides.
}
function applyTheme() {
  const value = themeAttribute(themeChoice);
  if (value) document.documentElement.dataset.theme = value;
  else delete document.documentElement.dataset.theme;
  $("theme").textContent = t(
    `ui.theme.${themeChoice === "light" || themeChoice === "dark" ? themeChoice : "system"}`,
  );
  $("theme").title = t("ui.theme.title");
  timeline?.refreshTheme();
  overview?.refreshTheme();
}
// The OS switching light/dark repaints the canvases too (the palette is resolved once per change).
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyTheme());
// Density: comfortable (default, roomy) or compact. The sizes the canvases
// and lanes.js need come from the tokens, so CSS stays the one source.
const DENSITY_KEY = "kuulas.density";
let densityChoice = "comfortable";
try {
  densityChoice = localStorage.getItem(DENSITY_KEY) === "compact" ? "compact" : "comfortable";
} catch {
  // Storage blocked: the default applies.
}
const tokenPx = (name) =>
  Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name));
function applyDensity() {
  const value = densityAttribute(densityChoice);
  if (value) document.documentElement.dataset.density = value;
  else delete document.documentElement.dataset.density;
  $("density").value = densityChoice;
  setState({
    density: densityChoice,
    laneHeight: clampLaneHeight(tokenPx("--lane-h")),
    busHeight: tokenPx("--bus-h"),
    groupGap: tokenPx("--group-gap"),
  });
}
$("density").addEventListener("change", (event) => {
  densityChoice = event.target.value === "compact" ? "compact" : "comfortable";
  try {
    localStorage.setItem(DENSITY_KEY, densityChoice);
  } catch {
    // Not remembered; it still applies now.
  }
  applyDensity();
});

// Show gates (WP44): a view option remembered per user; on by default.
const GATES_KEY = "kuulas.gates";
try {
  setState({ showGates: localStorage.getItem(GATES_KEY) !== "off" });
} catch {
  // Storage blocked: gates show.
}
$("show-gates").addEventListener("change", (event) => {
  setState({ showGates: event.target.checked });
  try {
    localStorage.setItem(GATES_KEY, event.target.checked ? "on" : "off");
  } catch {
    // Not remembered; it still applies now.
  }
});

// Animation: full / subtle / off (motion.js). Without a choice it follows
// the OS: reduced motion means off.
const MOTION_KEY = "kuulas.motion";
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
let motionChoice = null;
try {
  motionChoice = localStorage.getItem(MOTION_KEY);
} catch {
  // Storage blocked: follow the OS.
}
function applyMotion() {
  const mode = motionMode(motionChoice, reducedMotion.matches);
  document.documentElement.dataset.motion = mode;
  $("motion").value = mode;
}
$("motion").addEventListener("change", (event) => {
  motionChoice = event.target.value;
  try {
    localStorage.setItem(MOTION_KEY, motionChoice);
  } catch {
    // Not remembered; it still applies now.
  }
  applyMotion();
});
reducedMotion.addEventListener("change", () => applyMotion());

$("theme").addEventListener("click", () => {
  themeChoice = nextTheme(themeChoice);
  try {
    localStorage.setItem(THEME_KEY, themeChoice);
  } catch {
    // Not remembered; it still applies now.
  }
  applyTheme();
});

$("track-headers").addEventListener("scroll", (event) =>
  setState({ scrollY: event.target.scrollTop }),
);

function setLaneHeight(delta) {
  setState({ laneHeight: clampLaneHeight(getState().laneHeight + delta) });
}

// -- import: file picker and drag and drop ------------------------------------------------------

const importPanel = createImportPanel({
  root: $("import-panel"),
  t,
  actions: {
    undo: () => {
      importPanel.hide();
      $("undo").click();
    },
    sequence: () => void importSequentially(),
  },
});
// Anything else that changes the project takes the panel down: Undo would undo that instead.
subscribe(() => importPanel.sync(getState().head));

let lastImport = null; // { job, options } of the import the panel is about

async function importFiles(files, target = null) {
  if (files.length > 0) await runImport({ files }, target);
}

async function importPaths(paths, target = null) {
  if (paths.length > 0) await runImport({ paths }, target);
}

// `target`: where a drop landed (import-drop.js), null for the picker. `settled`: the
// exact options to send (the redo of an import), else the remembered choices apply.
async function runImport(job, target, settled = null) {
  const options = settled ?? importOptionsFor(target, importPanel.prefs());
  try {
    const result = job.files
      ? await api.uploadFiles(job.files, options)
      : await api.importPaths(job.paths, options);
    if (result.project) apply(result);
    const summary = summariseImport(result.report);
    if (summary.imported === 0 && summary.failures.length === 0) {
      showNotice(t("ui.import.failed"));
      return;
    }
    lastImport = { job, options };
    importPanel.show(panelModel(summary, options), getState().head);
  } catch (error) {
    showError(error);
  }
}

// "One after another instead": undo the import step, then bring the same files in again.
async function importSequentially() {
  const last = lastImport;
  if (!last) return;
  try {
    apply(await api.undo());
  } catch (error) {
    showError(error);
    return;
  }
  await runImport(last.job, null, { ...last.options, mode: "sequential" });
}

async function chooseMedia() {
  // The desktop window has a native dialog that gives paths to link in place;
  // a browser falls back to its own picker and uploads.
  const bridge = nativeBridge();
  if (!bridge) return $("file-input").click();
  try {
    await importPaths(await bridge.pick_media());
  } catch (error) {
    showError(error);
  }
}
$("import").addEventListener("click", () => void chooseMedia());
$("file-input").addEventListener("change", (event) => {
  const files = [...event.target.files];
  event.target.value = "";
  void importFiles(files);
});

let dragDepth = 0;
const setDrop = (on) => {
  $("drop").hidden = !on;
  if (!on) timeline.setDropPreview(null);
};
const draggedCount = (dataTransfer) =>
  Math.max(1, Array.from(dataTransfer.items ?? []).filter((item) => item.kind === "file").length);
// Over the timeline the ghost clips say what a drop does; elsewhere the plain drop card does.
function previewDrop(event) {
  const target = timeline.dropTarget(event, draggedCount(event.dataTransfer));
  timeline.setDropPreview(target);
  $("drop").hidden = target !== null;
  return target;
}
window.addEventListener("dragenter", (event) => {
  if (!dragHasFiles(event.dataTransfer)) return;
  event.preventDefault();
  dragDepth += 1;
  setDrop(true);
  previewDrop(event);
});
window.addEventListener("dragover", (event) => {
  if (!dragHasFiles(event.dataTransfer)) return;
  event.preventDefault();
  previewDrop(event);
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
  const target = timeline.dropTarget(event, draggedCount(event.dataTransfer));
  setDrop(false);
  // In the desktop window Python gets the dropped paths and calls
  // kuulasNative.importPaths; uploading the bytes as well would import twice.
  if (nativeBridge()) return;
  // The entries must be taken inside the event: a folder is only readable through them.
  const entries = [...(event.dataTransfer.items ?? [])]
    .map((item) => item.webkitGetAsEntry?.())
    .filter(Boolean);
  const files = [...event.dataTransfer.files];
  void collectDroppedFiles(entries, files)
    .then((found) => importFiles(found, target))
    .catch(showError);
});

// Called by the desktop window (src/kuulas/desktop.py): dropped paths and native menu items.
const menuActions = {
  "file.import": () => chooseMedia(),
  "file.export": () => $("export").click(),
  "edit.undo": () => $("undo").click(),
  "edit.redo": () => $("redo").click(),
  "view.zoom_in": () => $("zoom-in").click(),
  "view.zoom_out": () => $("zoom-out").click(),
  "view.density": () => {
    $("density").value = $("density").value === "compact" ? "comfortable" : "compact";
    $("density").dispatchEvent(new Event("change"));
  },
};
window.kuulasNative = {
  importPaths: (paths) => void importPaths(paths),
  menu: (id) => void menuActions[id]?.(),
};

// -- the canvases and panels -----------------------------------------------------------------------

let overview;
const trackHeaders = createTrackHeaders({
  root: $("track-headers"),
  editor,
  actions: {
    currentTrack: (id) => {
      if (getState().focusTrack !== id || getState().focusBus) {
        setState({ focusTrack: id, focusBus: null });
      }
    },
    currentBus: (id) => {
      if (getState().focusBus !== id) setState({ focusBus: id });
    },
  },
});
const inspector = createInspector({ root: $("panel-inspector"), editor });

// -- history (WP8) ------------------------------------------------------------------------------------

// Restore adds a step equal to an older one; the step left behind stays one Undo away.
async function restoreStep(node) {
  if (!node || node === getState().head) return;
  try {
    const response = await api.restore(node);
    apply(response);
    setState({ historySelected: response.head });
    showNotice(t("ui.history.restored"), "ok");
  } catch (error) {
    showError(error);
  }
}

const historyPanel = createHistoryPanel({
  root: $("panel-history"),
  api,
  getState,
  setState,
  actions: { restore: (node) => void restoreStep(node), showError },
});

// -- clipboard (WP46) -----------------------------------------------------------------------------------

async function refreshClipboard() {
  try {
    setState({ clipboard: (await api.getClipboard()).entries });
  } catch (error) {
    showError(error);
  }
}

// Copy changes no project: it has its own route. A new copy becomes the newest entry, so
// the tab's pick is dropped and Mod+V pastes what was just copied. Returns whether it worked.
async function copyToClipboard(body) {
  try {
    const answer = await api.copyToClipboard(body);
    setState({ clipboard: answer.entries, clipboardSelected: null });
    return true;
  } catch (error) {
    showError(error);
    return false;
  }
}

// Every entry action answers with the whole list, so the tab cannot drift from the file.
const clipboardAction = (call) => async () => {
  try {
    setState({ clipboard: (await call()).entries });
  } catch (error) {
    showError(error);
  }
};

// "Paste again" follows the tab's mode choice; the tab's target choice is read by the command.
const pasteCommand = (state) =>
  state.pasteMode === "overwrite" ? "edit.paste_overwrite" : "edit.paste";

const clipboardPanel = createClipboardPanel({
  root: $("panel-clipboard"),
  actions: {
    select: (id) => setState({ clipboardSelected: id }),
    pin: (id, pinned) => void clipboardAction(() => api.pinClipboardEntry(id, pinned))(),
    rename: (id, name) => void clipboardAction(() => api.renameClipboardEntry(id, name))(),
    remove: (id) => {
      if (getState().clipboardSelected === id) setState({ clipboardSelected: null });
      void clipboardAction(() => api.deleteClipboardEntry(id))();
    },
    choose: (patch) => setState(patch),
    canPasteAgain: (state) => keyboard.registry.can(pasteCommand(state), state),
    pasteAgain(id) {
      setState({ clipboardSelected: id });
      keyboard.registry.run(pasteCommand(getState()), null, getState());
    },
  },
});
// Another window of kuulas may have copied something: look again when this one is back.
window.addEventListener("focus", () => void refreshClipboard());

// -- help ---------------------------------------------------------------------------------------------

// Help reads the command registry and the keymap the user has (entries(): the
// defaults with their overrides), the same data the cheat sheet and menus read.
const help = createHelpPanel({
  root: $("panel-help"),
  keymap: () => keyboard.entries(),
  format: (combo) => keyboard.format(combo),
  commands: () => keyboard.registry.ids().filter((id) => keyboard.registry.status(id) === "ready"),
  runCommand: (id) => keyboard.registry.run(id, null, getState()),
  getContext() {
    const state = getState();
    const active = document.activeElement;
    return {
      control: active?.closest?.("[data-help-id]")?.dataset.helpId ?? null,
      empty: !state.project?.tracks?.length,
      panel: state.panel,
      inHeaders: Boolean(active && $("track-headers").contains(active)),
      selection: state.selection.size,
      focusTrack: state.focusTrack,
      focusBus: state.focusBus,
      // F1 on a menu item: the command it runs.
      command: active?.closest?.("#menubar [data-command]")?.dataset.command ?? null,
    };
  },
  async fetchText(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error(`${path}: ${response.status}`);
    return response.text();
  },
});
$("help-button").addEventListener("click", () => void help.open());

const timeline = createTimeline({
  stack: $("timeline-stack"),
  waveCanvas: $("wave"),
  overlayCanvas: $("timeline"),
  getState,
  actions: {
    pointerDown: onPointerDown,
    openGate: openGateStretch,
    wheel: onWheel,
    resized() {
      if (fitWhole && getState().project) fitWholeEdit();
      overview?.redraw();
    },
  },
});
overview = createOverview({
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
      "showGates",
      "focusTrack",
      "focusBus",
      "busHeight",
      "groupGap",
    )
  ) {
    timeline.redrawWaveforms();
  }
  if (touched("project", "scroll", "zoom", "playhead", "selection")) overview.redraw();
  if (touched("playhead", "project")) {
    $("timecode").textContent = frameToTime(state.playhead, rate());
  }
  if (touched("playing")) {
    $("play-icon").textContent = state.playing ? "■" : "▶";
    $("play-label").textContent = t(state.playing ? "ui.transport.stop" : "ui.transport.play");
  }
  if (touched("zoom", "project", "scroll")) {
    const view = t(views.current === "close" ? "ui.view.close" : "ui.view.wide");
    // The view's name is on the toggle beside it; the readout shows only the span.
    $("zoom-chip").textContent = spanText(state);
    $("zoom-chip").title = t("ui.zoom.label", { view, span: spanText(state) });
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
  if (touched("showGates")) $("show-gates").checked = state.showGates;
  if (touched("groupEditing")) {
    // A mode chip shows only when the safe default is off (design 8.2).
    const chip = $("group-chip");
    chip.hidden = state.groupEditing;
    chip.textContent = t("ui.mode.group_off");
    chip.title = t("ui.mode.group_off_title");
  }
  if (touched("waveformMode")) $("waveform-mode").value = state.waveformMode;
  if (touched("project", "focusTrack", "focusBus", "laneHeight", "busHeight", "groupGap"))
    trackHeaders.update(state);
  if (touched("project", "selection", "focusTrack", "focusBus")) inspector.update(state);
  if (touched("selection", "focusTrack", "focusBus", "panel")) help.update();
  if (
    touched(
      "clipboard",
      "clipboardSelected",
      "pasteMode",
      "pasteTarget",
      "project",
      "focusTrack",
      "playhead",
    )
  )
    clipboardPanel.update(state);
  if (touched("sidebarTab")) {
    for (const name of SIDEBAR_TABS) {
      $(`panel-${name}`).hidden = state.sidebarTab !== name;
      $(`tab-${name}`).setAttribute("aria-selected", String(state.sidebarTab === name));
      $(`tab-${name}`).tabIndex = state.sidebarTab === name ? 0 : -1;
    }
  }
  if (touched("head", "sidebarTab", "historySelected")) historyPanel.update(state);
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
  transcript.update(state, patch);
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
  importPanel.refresh();
  translate();
  applyTheme();
  render(getState(), null);
});

// -- start --------------------------------------------------------------------------------------------------

try {
  await initI18n({ document });
} catch (error) {
  console.error("the translations could not be loaded; showing message keys", error);
}
translate();
applyTheme();
applyDensity();
applyMotion();
render(getState(), null);

try {
  const [state, words] = await Promise.all([api.getState(), api.getWords()]);
  apply(state);
  setState({ words: words.words ?? [] });
  await refreshClipboard();
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
