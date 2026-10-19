// The editor's entry point: wires the store, the API, the live channel, the
// canvases and the keyboard together. The decisions live in small pure modules
// (view.js, lanes.js, keys.js, ...); this file only applies their answers.

import * as api from "./api.js";
import { createAutomixDialog } from "./automix-dialog.js";
import { automixNotice } from "./automix-model.js";
import { memberClipsAt, toggleChange } from "./bus-collapse.js";
import { listedRows, scrollToShow, stepTarget } from "./candidates-model.js";
import { createCandidatesPanel } from "./candidates-panel.js";
import { previewRequest } from "./candidates-preview.js";
import { clipDragChange } from "./clip-drag.js";
import { expandGroups, toggleGroupSelection } from "./clip-groups.js";
import { entryTitle } from "./clipboard.js";
import { createClipboardPanel } from "./clipboard-panel.js";
import { createClock } from "./clock.js";
import { createColabDialogs } from "./colab-dialog.js";
import {
  colabNotice,
  consentNeeded,
  rememberConsent,
  rememberedConsent,
  resumableJob,
} from "./colab-model.js";
import { openContextMenu } from "./context-menu.js";
import { contextMenuItems } from "./context-menu-model.js";
import { dragModeChoice, nextDragMode } from "./drag-mode.js";
import { edgeChange } from "./edge-drag.js";
import { createEditor } from "./edits.js";
import { escapeAction } from "./escape.js";
import { exportNotice, exportRequest, filenameFromDisposition } from "./export-commands.js";
import { createExportDialog } from "./export-dialog.js";
import {
  chipFast,
  dragSpeed,
  STEP as FAST_STEP,
  stepDown as fastDown,
  stepUp as fastUp,
  fromStored,
  MAX_FAST,
  MIN_FAST,
  reset as resetFast,
  setFast,
  toggle as toggleFast,
} from "./fast-speed.js";
import { nextPanel } from "./focus.js";
import { followScroll } from "./follow.js";
import { frameToTime, RATE, xToFrame } from "./format.js";
import { fadeChange, gainChange } from "./gain-drag.js";
import { GATE_OPEN_COMMAND, openStretchEdit, stretchAt } from "./gate.js";
import { HELP_COMMAND, shortcutsFor } from "./help.js";
import { createHelpPanel } from "./help-panel.js";
import { undoNotice } from "./history-model.js";
import { createHistoryPanel } from "./history-panel.js";
import {
  formatClock,
  formatNumber,
  formatShortcut,
  getLanguage,
  initI18n,
  onLanguageChange,
  t,
} from "./i18n.js";
import { installIcons } from "./icons.js";
import {
  collectDroppedFiles,
  createDropMemory,
  importOptionsFor,
  pickerPlacement,
} from "./import-drop.js";
import { createImportPanel, panelModel } from "./import-panel.js";
import { dragHasFiles, nativeBridge, summariseImport } from "./importing.js";
import { createInspector } from "./inspector.js";
import { formatCombo } from "./keymap-config.js";
import { detectPlatform, isTextField } from "./keys.js";
import {
  autoFitKey,
  explicitFit,
  fitHeight,
  scrollThumb,
  shouldAutoFit,
  withLaneHeight,
} from "./lane-sizing.js";
import { clampLaneHeight, layoutFor, pointerIntent, projectEnd, RULER_HEIGHT } from "./lanes.js";
import { leftOffHere, leftOffOf, leftOffText } from "./left-off.js";
import { createLevelMeter } from "./level-meter.js";
import { connectLive } from "./live.js";
import { createLocateDialog } from "./locate-dialog.js";
import { activeLoop } from "./loop-range.js";
import { createLoudnessLoader } from "./loudness-readout.js";
import { regionCount } from "./markers-model.js";
import { createMarkersPanel } from "./markers-panel.js";
import { createMarksCorner } from "./marks-corner.js";
import { missingNotice } from "./media-copy-model.js";
import { heldFromEvent } from "./modifiers.js";
import { monoDecision, monoEdits } from "./mono-ask.js";
import { motionMode } from "./motion.js";
import { createOverview } from "./overview.js";
import { createPlaceholderEditor } from "./placeholder-editor.js";
import { createPrefs } from "./prefs.js";
import { nextPreroll, prerollLabel } from "./preroll.js";
import { createProjectDialog } from "./project-dialog.js";
import { patchClip } from "./provisional.js";
import { rangeLine } from "./range-info.js";
import { rememberRange, stepRangeMemory } from "./range-memory.js";
import { createRecordView } from "./record-view.js";
import { forwardFromClip } from "./selection-ops.js";
import { createSendCopyDialog } from "./send-copy-dialog.js";
import { setupKeyboard } from "./shell-keys.js";
import { chipSpeed } from "./shuttle.js";
import { createStatsDialog } from "./stats-dialog.js";
import { nextStopMode } from "./stop-mode.js";
import { getState, reduceLive, serverPatch, setState, subscribe } from "./store.js";
import { createSyncConfirm } from "./sync-confirm.js";
import { driftingAmong, missingPartners } from "./sync-state.js";
import {
  cycleScope,
  headerFocusPatch,
  nextStop,
  prevStop,
  SCOPE_MODE,
  scopeChoice,
  scopeIndicatorKey,
  stopsForScope,
  wordsAreCurrent,
} from "./tab-stops.js";
import { densityAttribute, nextTheme, themeAttribute } from "./theme.js";
import { createTimeline } from "./timeline.js";
import { contextPress, menuFromSections, timelineMenuItems } from "./timeline-menu.js";
import { createTrackHeaders } from "./tracks.js";
import { createTranscript } from "./transcript.js";
import { mutedInputsKey, pauseChoiceId } from "./transcript-model.js";
import { createTransport } from "./transport.js";
import * as View from "./view.js";
import { changeKey, createSaver, recordOf, restoreFrom } from "./view-memory.js";
import { nextWheelMode, wheelModeChoice } from "./wheel.js";

const $ = (id) => document.getElementById(id);
installIcons();
const prefs = createPrefs();
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
// `sticky`: it stays until replaced or closed (a running export). `action`: { label, run }
// shows one more button (Cancel, Show in Finder).
let noticeAction = null;
function showNotice(text, kind = "error", { undo = false, sticky = false, action = null } = {}) {
  const notice = $("notice");
  $("notice-text").textContent = text;
  $("notice-undo").hidden = !undo;
  noticeAction = action;
  $("notice-action").hidden = !action;
  if (action) $("notice-action").textContent = action.label;
  notice.dataset.kind = kind;
  notice.hidden = false;
  clearTimeout(noticeTimer);
  if (sticky) return;
  noticeTimer = setTimeout(() => {
    notice.hidden = true;
  }, NOTICE_MS[kind]);
}
$("notice-action").addEventListener("click", () => noticeAction?.run());
const showError = (error) => showNotice(error?.message || t("ui.error.title"));
$("notice-close").addEventListener("click", () => {
  $("notice").hidden = true;
});
$("notice-undo").addEventListener("click", () => {
  $("notice").hidden = true;
  undo();
});

// -- server state -----------------------------------------------------------

let fitWhole = true; // the view shows the whole edit and keeps doing so on resize/import
let views = View.initialViews();
let history = View.createViewHistory();
let settleTimer = null;
let wheelAnchor = 0;
let exportFormatIds = null; // the export formats the server offers; null until fetched
let exportFormatList = null; // the same as [{ id, label, ... }], for the export dialog

const rate = () => getState().project?.rate ?? RATE;
const totalFrames = () => projectEnd(getState().project);
const width = () => Math.max(1, timeline?.size().width ?? 1);
const viewLevels = () =>
  View.zoomLevels({ width: width(), rate: rate(), totalFrames: totalFrames() });
const bounds = () => ({ width: width(), totalFrames: totalFrames() });

function apply(response) {
  const patch = serverPatch(response, getState());
  // What the server's mute/solo state is, for the transcript's struck-through words; the
  // project on screen may hold a provisional toggle the server has not answered yet.
  if (response.project) patch.serverMutedKey = mutedInputsKey(response.project);
  setState(patch);
  if (fitWhole) fitWholeEdit();
  // An export that left unrecorded narration silent says so (WP43): a warning, not a refusal.
  const skipped = response.export?.placeholders_skipped ?? 0;
  if (skipped > 0) showNotice(t("ui.export.placeholders_skipped", { count: skipped }), "ok");
}

async function refresh() {
  apply(await api.getState());
}

// -- sync states (R51, WP19a) -----------------------------------------------------
// The server decides which clips are drifting or free; the page asks after every edit (the answer
// is memoized there) and again for the partners of a new selection. Nothing resyncs by itself.

async function refreshSync() {
  try {
    const answer = await api.getSync();
    setState({ syncClips: answer.clips, syncAnchors: answer.anchors ?? [] });
  } catch {
    // The badges are a help: a failed look leaves the last ones, the next edit looks again.
  }
}

async function refreshPartners() {
  const { selection, partners } = getState();
  const missing = missingPartners(partners, selection);
  if (missing.length === 0) return;
  try {
    const answer = await api.getPartners(missing);
    setState({ partners: { ...getState().partners, ...answer.partners } });
  } catch {
    // No outline this time.
  }
}

/** A server command that resyncs: apply the answer and say how many clips moved and how many were free. */
async function syncCommand(name, args) {
  try {
    const response = await api.command(name, args);
    apply(response);
    // Undo only when something moved: a resync that did nothing made no step.
    if (response.resync?.message)
      showNotice(response.resync.message, "ok", { undo: response.resync.resynced > 0 });
    return response;
  } catch (error) {
    showError(error);
    return null;
  }
}

// Sync asks first (owner, 2026-10-19): "Confirm before re-syncing" is on until switched off in the
// View menu; remembered per user.
const CONFIRM_SYNC_KEY = "confirmSync";
setState({ confirmSync: prefs.get(CONFIRM_SYNC_KEY) !== "off" });
function toggleConfirmSync() {
  const on = getState().confirmSync === false;
  setState({ confirmSync: on });
  prefs.set(CONFIRM_SYNC_KEY, on ? "on" : "off");
  showNotice(t(on ? "ui.sync.confirm.on" : "ui.sync.confirm.off"), "ok");
}
let syncConfirm = null;
const confirmSync = (preview) => {
  syncConfirm ??= createSyncConfirm({ t, format: (value) => formatNumber(value, { digits: 2 }) });
  return syncConfirm.ask(preview);
};
async function syncPreview(name, args) {
  try {
    return await api.syncPreview(name, args);
  } catch (error) {
    showError(error);
    return null;
  }
}

/**
 * After a clip was moved alone (Alt held) the clips that now drift get one question, nothing more:
 * "Keep this clip free from sync?" with Free it; closing the message says No. Nothing changes
 * unless it is answered.
 */
async function askToFree(ids) {
  await refreshSync();
  const drifting = driftingAmong(getState().syncClips, ids);
  if (drifting.length === 0) return;
  showNotice(t("ui.sync.prompt"), "ok", {
    sticky: true,
    action: {
      label: t("ui.sync.prompt_yes"),
      run: () => {
        $("notice").hidden = true;
        editor.change({
          op: "set_free",
          args: { clip_ids: drifting, free: true },
          label: t("ui.sync.history.free"),
        });
      },
    },
  });
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

// Fast listening (WP26): a toggle plus a stepless chosen speed, remembered per user. The state
// changes first, then the engine is told (a switch restarts the run, a nudge retunes it).
// What a mouse drag does (drag-mode.js): a per-user preference; the default paints a range.
const DRAG_MODE_KEY = "dragMode";
setState({ dragMode: dragModeChoice(prefs.get(DRAG_MODE_KEY)) });
function toggleDragMode() {
  const mode = nextDragMode(getState().dragMode);
  setState({ dragMode: mode });
  prefs.set(DRAG_MODE_KEY, mode);
  showNotice(t(`ui.drag_mode.now_${mode}`), "ok");
}

// What a two-finger trackpad scroll does (wheel.js): a per-user preference; the default zooms.
const WHEEL_MODE_KEY = "wheelMode";
setState({ wheelMode: wheelModeChoice(prefs.get(WHEEL_MODE_KEY)) });
function toggleWheelMode() {
  const mode = nextWheelMode(getState().wheelMode);
  setState({ wheelMode: mode });
  prefs.set(WHEEL_MODE_KEY, mode);
  showNotice(t(`ui.wheel_mode.now_${mode}`), "ok");
}

// Words in the clips on the timeline (clip-words.js, WP69): on by default, remembered per user.
const CLIP_WORDS_KEY = "clipWords";
setState({ showClipWords: prefs.get(CLIP_WORDS_KEY) !== "off" });
function toggleClipWords() {
  const on = getState().showClipWords === false;
  setState({ showClipWords: on });
  prefs.set(CLIP_WORDS_KEY, on ? "on" : "off");
  showNotice(t(on ? "ui.clip_words.on" : "ui.clip_words.off"), "ok");
}

const FAST_KEY = "fast";
setState({ fast: fromStored(prefs.getJson(FAST_KEY, null)) });
function changeFast(change) {
  const before = getState().fast;
  const after = change(before);
  if (after.fast === before.fast && after.active === before.active) return;
  setState({ fast: after });
  prefs.setJson(FAST_KEY, after);
  void transport.fastChanged(before, after);
}

const actions = {
  togglePlay: () => void transport.toggle(),
  playFrom: (frame) => void transport.play(frame),
  playRequest: (request) => {
    if (request) void transport.preview(request.at, request.until, request.skip);
  },
  shuttle: (key) => void transport.press(key),
  toggleLoop: () => setState({ loop: !getState().loop }),
  toggleDragMode: () => toggleDragMode(),
  toggleWheelMode: () => toggleWheelMode(),
  toggleClipWords: () => toggleClipWords(),
  fastListening: () => changeFast(toggleFast),
  fastNudge: (direction) => changeFast(direction > 0 ? fastUp : fastDown),
  fastReset: () => changeFast(resetFast),
  fastSet: (value) => changeFast((state) => setFast(state, value)),
  goHome() {
    const active = document.activeElement;
    const state = getState();
    const what = escapeAction({
      inTextField: isTextField(active),
      selection: state.selection,
      rangeTracks: state.rangeTracks,
      inPoint: state.inPoint,
      outPoint: state.outPoint,
    });
    if (what === "blur") active.blur();
    // Clear the clip selection, the range and the in and out marks (owner, 2026-10-18).
    if (what === "clear") {
      setState({ selection: new Set(), rangeTracks: new Set(), inPoint: null, outPoint: null });
    } else focusPanel("timeline");
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
    if (!getState().project) return;
    fitWholeEdit();
    history = View.visitView(history, { zoom: getState().zoom, scroll: getState().scroll });
  },
  fitSelection() {
    const state = getState();
    if (!state.project) return;
    const target = View.fitTarget(state);
    if (target.end <= target.start) return;
    if (target.start === 0 && target.end === totalFrames()) fitWholeEdit();
    else setView(View.fitRange({ ...target, width: width() }));
    history = View.visitView(history, { zoom: getState().zoom, scroll: getState().scroll });
  },
  /** View > Break paragraphs at pauses over: remembered per user, applied at once. */
  setPauseBreak(choice) {
    const id = pauseChoiceId(choice);
    prefs.set(PAUSE_BREAK_KEY, id);
    setState({ pauseBreak: id });
  },
  tabStop: (direction) => void tabStop(direction),
  /** Alt+Tab (Shift+T): word, edge or sound scope, remembered per user, named in a notice. */
  cycleTabScope() {
    const scope = cycleScope(tabScope());
    prefs.set(TAB_SCOPE_KEY, scope);
    showNotice(t(`ui.tab_scope.${scope}`), "ok");
    updateTabScope();
  },
  fitTracks: () => fitAllTracks(),
  toggleAutoFitTracks() {
    const on = !getState().autoFitTracks;
    lastFitKey = "";
    setState({ autoFitTracks: on });
    showNotice(t(on ? "ui.view.auto_fit_on" : "ui.view.auto_fit_off"), "ok");
  },
  viewBack: () => stepHistory(View.backView),
  resetRememberedView() {
    fitWholeEdit();
    setState({
      laneHeight: clampLaneHeight(tokenPx("--lane-h")),
      laneHeights: {},
      autoFitTracks: false,
      collapsedBuses: new Set(),
      waveformMode: "half",
      followMode: "page",
      sidebarTab: "inspector",
      inPoint: null,
      outPoint: null,
    });
    viewSaver.touch(currentRecord);
    viewSaver.flush();
    showNotice(t("ui.view.reset_remembered_done"), "ok");
  },
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

// The marks a cut used up come back on Undo (range-memory.js).
let rangeMemory = null;

// -- pointer on the timeline ------------------------------------------------------

function onPointerDown(hit, event, { noSeek = false } = {}) {
  // The click rule lives in lanes.js pointerIntent (tested): anywhere in the
  // lane area sets the play cursor, a clip is also selected, Shift only toggles.
  const mod = heldFromEvent(event, detectPlatform()).mod;
  const additive = event.shiftKey || mod;
  const intent = pointerIntent(hit, { shift: event.shiftKey, mod });
  if (!intent) return;
  const state = getState();
  const patch = { panel: "timeline", rangeTracks: new Set() };
  if (hit.row?.kind === "track" && !additive) {
    patch.focusTrack = hit.row.id;
    patch.focusBus = null;
    // The range's tracks (Select > Range on all tracks) end with a click elsewhere.
    patch.rangeTracks = new Set();
  } else if (hit.row?.kind === "bus" && !additive) patch.focusBus = hit.row.id;
  // A narration placeholder is picked like a clip (WP43): one at a time, never with a clip.
  if (!additive)
    patch.placeholderSelected = hit.placeholder && !hit.clip ? hit.placeholder.id : null;
  if (mod && event.altKey && hit.clip && hit.row?.kind === "track") {
    // Cmd+Alt+click (Hindenburg): this clip and every clip after it, on all tracks.
    patch.selection = expandGroups(state.project, forwardFromClip(state.project, hit.clip.id));
  } else if (event.shiftKey && hit.row?.kind === "bus" && hit.row.collapsed) {
    // Shift+click on a folded bus: add the member clips under the pointer to the selection.
    const selection = new Set(state.selection);
    for (const id of memberClipsAt(state.project, hit.row.id, hit.frame)) selection.add(id);
    patch.selection = expandGroups(state.project, selection);
  } else if (intent.selection === "replace")
    patch.selection = expandGroups(state.project, [intent.clip.id]);
  else if (intent.selection === "clear") patch.selection = new Set();
  else if (intent.selection === "toggle")
    patch.selection = toggleGroupSelection(state.project, state.selection, intent.clip.id);
  setState(patch);
  if (intent.seek !== null && !noSeek) void transport.seek(intent.seek);
}

// A dragged range (WP6) is the in and out marks, so every edit that acts on marks acts on
// it. The edit plans take one track (the focus track), so the lanes covered are kept in
// `rangeTracks` for when they take a set. Released with Alt held it is the clips the drag
// touched (`selection`), the marks at their span and their tracks.
function onRangeDragged({ start, end, tracks, trackId, selection }) {
  setState({
    ...(selection ? { selection } : {}),
    inPoint: start,
    outPoint: end,
    rangeTracks: new Set(tracks),
    focusTrack: trackId,
    focusBus: null,
  });
}

// -- keyboard focus ------------------------------------------------------------------

const panelElements = {
  timeline: $("timeline"),
  transcript: $("panel-transcript"),
  inspector: $("panel-inspector"),
  candidates: $("panel-candidates"),
  clipboard: $("panel-clipboard"),
  markers: $("panel-markers"),
  history: $("panel-history"),
};
const SIDEBAR_TABS = ["inspector", "candidates", "clipboard", "markers", "history"];

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

/** Download a file the server builds (subtitles, transcript text); -> its name, or null. */
async function downloadFile(path, fallback) {
  try {
    const { blob, disposition } = await api.download(path);
    const name = filenameFromDisposition(disposition, fallback);
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 10_000);
    return name;
  } catch (error) {
    showError(error);
    return null;
  }
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
    transcribeColab: (ids) => void transcribeOnColab(ids),
  },
});

// The whole keyboard layer: keymap, palette, cheat sheet, menu bar, hints (shell-keys.js).
const keyboard = setupKeyboard({
  actions,
  prefs,
  t,
  notify: showNotice,
  onLanguageChange,
  // Help search (WP75) lists matching help topics and opens one on a click; `help` is made below.
  help: {
    topics: () => help.topics(),
    load: () => help.load(),
    open: (id) => void help.openTopic(id),
  },
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
    undo: () => undo(),
    redo: () => redo(),
    restoreStep: () => restoreStep(getState().historySelected),
    openHistory: () => focusPanel("history"),
    edit: (change) => editor.change(change),
    toast: (text, options) => showNotice(text, "ok", options),
    copy: (body) => copyToClipboard(body),
    refreshClipboard: () => void refreshClipboard(),
    clearOldClipboard: (keep) => clearOldClipboard(keep),
    shareClipboard: (id, on) => shareClipboardEntry(id, on),
    showClipboard: (view) => showClipboard(view),
    openClipboardProject: () => void openClipboardProject(),
    rememberRange: () => {
      const { head, inPoint, outPoint, rangeTracks } = getState();
      rangeMemory = rememberRange(head, { inPoint, outPoint, rangeTracks });
    },
    previewClipboard: (id) =>
      api.previewClipboardEntry(id).catch((error) => {
        showError(error);
        return null;
      }),
    now: () => performance.now(),
    chooseMedia: () => chooseMedia(),
    // The transcript's X: cut the words' stretch on every track.
    cutWords: (indices) =>
      api
        .command("cut_words", { indices, group_editing: getState().groupEditing !== false })
        .then((response) => {
          apply(response);
          return true;
        })
        .catch((error) => {
          showError(error);
          return false;
        }),
    correct: () => transcript.startCorrect(),
    openFind: () => {
      focusPanel("transcript");
      transcript.openFind();
    },
    // Match loudness measures for seconds; the answer carries the report.
    matchLoudness: (clipIds, target) =>
      api
        .command("match_loudness", { clip_ids: clipIds, target_lufs: target })
        .then((response) => {
          apply(response);
          return response.match_report;
        })
        .catch((error) => {
          showError(error);
          return null;
        }),
    // A plain server command (save_backup, save_checkpoint): the answer, or null after
    // showing the error (a read-only project says who has it open).
    command: (name, args) =>
      api.command(name, args).catch((error) => {
        showError(error);
        return null;
      }),
    syncCommand: (name, args) => syncCommand(name, args),
    syncPreview: (name, args) => syncPreview(name, args),
    confirmSync: (preview) => confirmSync(preview),
    confirmEnabled: () => getState().confirmSync !== false,
    toggleConfirmSync: () => toggleConfirmSync(),
    notice: (text) => showNotice(text, "ok"),
    clock: () => new Date(),
    // A save is also where the user left off: the flag moves here and resume.json is
    // written at once (flushView sends the record marked "now").
    markLeftOff() {
      setState({ leftOff: leftOffHere(getState().playhead, new Date()) });
      flushView();
    },
    download: (path, fallback) => downloadFile(path, fallback),
    promptText: (request) => placeholderEditor.prompt(request),
    takeFor: (id) => void takeForPlaceholder(id),
    exportRegions: () => exportRegions(),
    automix: () => void openAutomix(),
    openStatistics: () => void openStatistics(),
    openLocateMedia: () => void openLocateMedia(),
    openSendCopy: () => void openSendCopy(),
    openRecord: () => void recordView.open(),
    cycleStopMode: () => cycleStopMode(),
    cyclePreroll: () => cyclePreroll(),
    autoSilence: () => void autoSilence(),
    duckMicrophones: () => void duckMicrophones(),
    transcribeTrack: (backend) => void transcribeTrack(backend),
    restartTranscriptions: () => void restartTranscriptions(),
    openColabSettings: () => void colabDialogsFor().openSettings(),
    exportTracks: (format, options) => exportTracks(format, options),
    exportMix: (format, options) => exportMix(format, options),
    exportFormats: () => exportFormatIds,
    openExportDialog: (what) => openExportDialog(what),
    newProject: () => void newProject(),
    openProject: () => void openProject(),
    focusName: () => inspector.focusName(),
    editTime: () => clock.open(),
    copyTime: () => void clock.copy(),
    openGateStretch: () => openGateStretch(),
    selectCandidate: (row) => selectCandidate(row),
    findCandidates: () => void findCandidates(),
    applyCandidate: (id, mode) => void applyCandidate(id, mode),
    keepCandidate: (id) => void keepCandidate(id),
    markCandidate: (start, end, track) => void markCandidate(start, end, track),
    previewCandidate: (row) => void previewCandidate(row),
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
// Record sits beside Play: the same command as Transport > Record… (no key of its own yet).
$("record").addEventListener("click", () =>
  keyboard.registry.run("transport.record", null, getState()),
);
$("loop").addEventListener("click", () =>
  keyboard.registry.run("transport.loop", null, getState()),
);
// Undo and redo say so when they pass a session marker: "Undid a step from yesterday: ...".
const moveHistory = (call) => () =>
  void call()
    .then((response) => {
      apply(response);
      const notice = undoNotice(response.moved, Date.now(), t);
      if (notice) showNotice(notice, "ok");
    })
    .catch(showError);
const undo = moveHistory(api.undo);
const redo = moveHistory(api.redo);
$("zoom-in").addEventListener("click", () => actions.zoomStep(1));
$("zoom-out").addEventListener("click", () => actions.zoomStep(-1));
$("view-toggle").addEventListener("click", () => actions.toggleView());
$("fit").addEventListener("click", () => actions.fitView());
$("waveform-mode").addEventListener("change", (event) =>
  setState({ waveformMode: event.target.value }),
);
$("waveform-gain").addEventListener("click", () => setState({ waveformGain: 1 }));
// The chip: fast listening on -> a click switches it off; a shuttle speed -> plays normally.
// With fast listening on, the chip is also a handle: drag it left or right to change the speed
// (owner, 2026-10-18); a press that does not travel is the click that switches it off.
const speedChip = $("speed-chip");
let chipDrag = null;
speedChip.addEventListener("pointerdown", (event) => {
  if (event.button !== 0 || !getState().fast.active) return;
  chipDrag = { x: event.clientX, start: getState().fast.fast, moved: false };
  speedChip.setPointerCapture?.(event.pointerId);
});
speedChip.addEventListener("pointermove", (event) => {
  if (!chipDrag) return;
  const dx = event.clientX - chipDrag.x;
  if (!chipDrag.moved && Math.abs(dx) < 4) return;
  chipDrag.moved = true;
  actions.fastSet(dragSpeed(chipDrag.start, dx));
});
speedChip.addEventListener("pointerup", () => {
  // The click that follows a drag must not switch fast listening off.
  if (chipDrag?.moved) speedChip.dataset.dragged = "1";
  chipDrag = null;
});
speedChip.addEventListener("click", () => {
  if (speedChip.dataset.dragged) {
    delete speedChip.dataset.dragged;
    return;
  }
  if (getState().fast.active) actions.fastListening();
  else void transport.play(getState().playhead);
});
const fastSlider = $("fast-speed");
fastSlider.min = String(MIN_FAST);
fastSlider.max = String(MAX_FAST);
fastSlider.step = String(FAST_STEP);
fastSlider.addEventListener("input", () => actions.fastSet(Number(fastSlider.value)));
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
const THEME_KEY = "theme";
let themeChoice = prefs.get(THEME_KEY) ?? "system"; // no storage: the OS decides
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
const DENSITY_KEY = "density";
let densityChoice = prefs.get(DENSITY_KEY) === "compact" ? "compact" : "comfortable";
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
  prefs.set(DENSITY_KEY, densityChoice); // not remembered if storage is blocked; it applies now
  applyDensity();
});

// Tab and Shift+Tab (WP19i): what the playhead jumps to. The scope (word, edge, sound) is
// remembered per user; until the user picks one it follows the project: words when there is
// a transcript, else clip borders. An old remembered "transient" or "both" is migrated.
// A new key: the old one may hold a "word" chosen before edges became the default.
const TAB_SCOPE_KEY = "tabScope";
const tabScope = () => scopeChoice(prefs.get(TAB_SCOPE_KEY), getState().words.length > 0);

/** The scope shown beside the range info: "Tab: words". */
function updateTabScope() {
  const el = $("tab-scope");
  if (!el) return;
  const text = t(scopeIndicatorKey(tabScope()));
  if (el.textContent !== text) el.textContent = text;
}

// Server stops (clip borders, transients) per head, mode and track, kept as promises so a
// held Tab asks once. A new head is a new key, so an edit never serves the old stops.
let editPointCache = { head: null, stops: new Map() };
function serverStops(mode, track) {
  const { head } = getState();
  if (editPointCache.head !== head) editPointCache = { head, stops: new Map() };
  const key = `${mode}|${track ?? ""}`;
  if (!editPointCache.stops.has(key)) {
    const asked = api
      .getEditPoints(mode, track)
      .then((body) => body.points)
      .catch((error) => {
        editPointCache.stops.delete(key);
        throw error;
      });
    editPointCache.stops.set(key, asked);
  }
  return editPointCache.stops.get(key);
}

// The words are derived from the edit. The transcript panel reloads them on a head change,
// but not before Tab can be pressed (or at all while it is not built): make sure the words
// in the state are the ones of the head now. One request at a time.
let wordsAsked = null; // { head, promise }
async function ensureWords() {
  while (!wordsAreCurrent(getState())) {
    const { head } = getState();
    if (head === null || head === undefined) return;
    if (wordsAsked?.head !== head) {
      const asked = { head, promise: api.getWords() };
      wordsAsked = asked;
      const clear = () => {
        if (wordsAsked === asked) wordsAsked = null;
      };
      asked.promise.then(clear, clear);
    }
    const body = await wordsAsked.promise;
    // Only if the edit did not move on while it was in flight, else ask again.
    if (getState().head === head) {
      setState({ words: body.words ?? [], people: body.people ?? {}, wordsHead: head });
    }
  }
}

async function tabStop(direction) {
  const state = getState();
  if (!state.project) return;
  const scope = tabScope();
  const track = state.focusTrack ?? null;
  try {
    let stops;
    if (scope === "word") {
      await ensureWords();
      stops = stopsForScope(scope, {
        words: getState().words,
        track,
        markers: state.project.markers,
      });
    } else {
      // Seams are on any track; sounds follow the focused track.
      const serverTrack = scope === "edge" ? null : track;
      stops = stopsForScope(scope, {
        server: await serverStops(SCOPE_MODE[scope], serverTrack),
        markers: state.project.markers,
      });
    }
    const from = getState().playhead ?? 0;
    const frame = direction > 0 ? nextStop(stops, from) : prevStop(stops, from);
    if (frame === null) showNotice(t("ui.tab_stop.none"), "ok");
    else void transport.seek(frame);
  } catch (error) {
    showError(error);
  }
}

// Break paragraphs at pauses over (View menu): a view option remembered per user.
const PAUSE_BREAK_KEY = "pauseBreak";
setState({ pauseBreak: pauseChoiceId(prefs.get(PAUSE_BREAK_KEY)) });

// Show gates (WP44): a view option remembered per user; on by default.
const GATES_KEY = "gates";
setState({ showGates: prefs.get(GATES_KEY) !== "off" });
$("show-gates").addEventListener("change", (event) => {
  setState({ showGates: event.target.checked });
  prefs.set(GATES_KEY, event.target.checked ? "on" : "off");
});

// Animation: full / subtle / off (motion.js). Without a choice it follows
// the OS: reduced motion means off.
const MOTION_KEY = "motion";
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
let motionChoice = prefs.get(MOTION_KEY); // null: follow the OS
function applyMotion() {
  const mode = motionMode(motionChoice, reducedMotion.matches);
  document.documentElement.dataset.motion = mode;
  $("motion").value = mode;
}
$("motion").addEventListener("change", (event) => {
  motionChoice = event.target.value;
  prefs.set(MOTION_KEY, motionChoice);
  applyMotion();
});
reducedMotion.addEventListener("change", () => applyMotion());

$("theme").addEventListener("click", () => {
  themeChoice = nextTheme(themeChoice);
  prefs.set(THEME_KEY, themeChoice);
  applyTheme();
});

$("track-headers").addEventListener("scroll", (event) =>
  setState({ scrollY: event.target.scrollTop }),
);

// The - and + buttons are a manual choice: they switch auto-fit off.
function setLaneHeight(delta) {
  setState({ laneHeight: clampLaneHeight(getState().laneHeight + delta), autoFitTracks: false });
}

// Fit the lanes to the window: the lane area is the timeline minus the ruler.
const laneArea = () => $("timeline-stack").clientHeight - RULER_HEIGHT;
const fitInput = (state) => ({
  project: state.project,
  available: laneArea(),
  busHeight: state.busHeight,
  groupGap: state.groupGap,
  laneHeights: state.laneHeights,
  collapsed: state.collapsedBuses,
});
function fitTracks() {
  const state = getState();
  const height = fitHeight(fitInput(state));
  if (height !== null && height !== state.laneHeight) setState({ laneHeight: height });
}
// View > Fit tracks to window is explicit, so it means every track: hand-sized lanes are cleared.
function fitAllTracks() {
  const fit = explicitFit(fitInput(getState()));
  if (fit) setState(fit);
}
// The lanes area scrolls when even the smallest lanes do not fit; a thumb shows where.
function updateLanesScroll(state) {
  const thumb = scrollThumb({
    contentHeight: layoutFor(state).height,
    viewHeight: laneArea(),
    scrollY: state.scrollY,
  });
  const bar = $("lanes-scroll");
  bar.hidden = thumb === null;
  if (thumb) {
    bar.firstElementChild.style.top = `${thumb.top}px`;
    bar.firstElementChild.style.height = `${thumb.height}px`;
  }
}

// Auto-fit: refit when what moves the lanes changes (lane-sizing.js decides). Called
// from render and from the resize hook; the fit itself runs after the current
// listeners, because setState inside a listener would leave the later ones with a
// stale state.
let lastFitKey = "";
function autoFit(state) {
  if (!state.autoFitTracks) {
    lastFitKey = "";
    return;
  }
  const key = autoFitKey(fitInput(state));
  if (!shouldAutoFit({ on: true, key, last: lastFitKey })) return;
  lastFitKey = key;
  queueMicrotask(fitTracks);
}

// -- narration placeholders (WP43) ---------------------------------------------------------------------

const placeholderEditor = createPlaceholderEditor({ root: $("placeholder-editor"), t });

// Record it in place: pick one file and it replaces the placeholder, later material moving by
// the difference in length, as one undo step. The desktop window links the file by path; a
// browser uploads it.
async function takeForPlaceholder(placeholderId) {
  const done = (response) => {
    apply(response);
    showNotice(t("ui.placeholders.take_done"), "ok", { undo: true });
  };
  try {
    const bridge = nativeBridge();
    if (bridge) {
      const [path] = await bridge.pick_media();
      if (path)
        done(await api.command("placeholder_take", { placeholder_id: placeholderId, path }));
      return;
    }
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "audio/*,video/*";
    input.addEventListener("change", async () => {
      const file = input.files?.[0];
      if (!file) return;
      try {
        done(await api.uploadTake(placeholderId, file));
      } catch (error) {
        showError(error);
      }
    });
    input.click();
  } catch (error) {
    showError(error);
  }
}

// -- import: file picker and drag and drop ------------------------------------------------------

const importPanel = createImportPanel({
  root: $("import-panel"),
  t,
  actions: {
    undo: () => {
      importPanel.hide();
      undo();
    },
    sequence: () => void importSequentially(),
    mono: (tracks) => turnIntoMono(tracks),
    keepStereo: () => {},
  },
});
// Anything else that changes the project takes the panel down: Undo would undo that instead.
subscribe(() => importPanel.sync(getState().head));

let lastImport = null; // { job, options } of the import the panel is about

// One undoable step per track: the user can take back one voice and keep the other.
function turnIntoMono(tracks) {
  for (const edit of monoEdits(tracks)) {
    editor.change({ ...edit, label: t(edit.labelKey), labelKey: undefined });
  }
}

const dropMemory = createDropMemory();

async function importFiles(files, target = null) {
  if (files.length > 0) await runImport({ files }, target);
}

async function importPaths(paths, target = null) {
  if (paths.length > 0) await runImport({ paths }, target);
}

// `target`: where a drop landed (import-drop.js), null for the picker. `settled`: the
// exact options to send (the redo of an import), else the remembered choices apply.
async function runImport(job, target, settled = null) {
  let options = settled ?? importOptionsFor(target, importPanel.prefs());
  if (!settled && target === null) {
    // The picker: onto the selected track when there is one (import-drop.js pickerPlacement).
    const here = pickerPlacement(getState().project, getState().focusTrack, getState().playhead);
    if (here) options = { ...options, ...here };
  }
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
    // New stereo speech tracks: turn into mono, keep, or ask (the remembered choice).
    const decision = monoDecision(importPanel.prefs().mono, result.stereo);
    if (decision.action === "mono") turnIntoMono(decision.tracks);
    const asking = decision.action === "ask" ? decision.tracks : [];
    importPanel.show(panelModel(summary, options, asking), getState().head);
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
  // kuulasNative.importPaths; uploading the bytes as well would import twice. The place of the
  // drop is remembered for those paths (they would otherwise go to the play cursor).
  if (nativeBridge()) {
    dropMemory.remember(target, Date.now());
    return;
  }
  // The entries must be taken inside the event: a folder is only readable through them.
  const entries = [...(event.dataTransfer.items ?? [])]
    .map((item) => item.webkitGetAsEntry?.())
    .filter(Boolean);
  const files = [...event.dataTransfer.files];
  void collectDroppedFiles(entries, files)
    .then((found) => importFiles(found, target))
    .catch(showError);
});

// Called by the desktop window (src/kuulas/desktop.py): dropped paths. The native menu bar holds
// no menus of ours; every command lives in the in-window bar.
window.kuulasNative = {
  importPaths: (paths) => void importPaths(paths, dropMemory.take(Date.now())),
};

// -- the canvases and panels -----------------------------------------------------------------------

let overview;
// "New bus…" (header pop-up or Track section): focus the bus and start renaming it.
const nameNewBus = (id) => {
  setState({ focusBus: id, focusTrack: null });
  inspector.focusName();
};
const trackHeaders = createTrackHeaders({
  root: $("track-headers"),
  editor,
  onBusCreated: nameNewBus,
  actions: {
    currentTrack: (id) => {
      // A header is the timeline's keyboard context (Tab, arrows); the panel was left as it was.
      const patch = headerFocusPatch(getState());
      if (getState().focusTrack !== id || getState().focusBus || patch) {
        setState({ focusTrack: id, focusBus: null, ...patch });
      }
    },
    // The kind tag in a track header: focus the track, then the same command as Alt+Mod+K.
    cycleKind: (id) => {
      setState({ focusTrack: id, focusBus: null });
      keyboard.registry.run("track.cycle_kind", null, getState());
    },
    currentBus: (id) => {
      const patch = headerFocusPatch(getState());
      if (getState().focusBus !== id || patch) setState({ focusBus: id, ...patch });
    },
    // The chevron and a double-click on a bus header: fold or unfold it.
    toggleBus: (id) =>
      setState({
        collapsedBuses: toggleChange(getState(), id),
        focusBus: id,
        focusTrack: null,
      }),
    contextMenu: (kind, id, event) => showHeaderMenu(kind, id, event),
    // Drag a lane's bottom border (null resets it to the global height).
    setLaneHeight: (id, height) =>
      setState({ laneHeights: withLaneHeight(getState().laneHeights, id, height) }),
  },
});
// Right-click on a track or bus header: focus it, then offer its commands.
function showHeaderMenu(kind, id, event) {
  event.preventDefault();
  if (kind === "track") setState({ focusTrack: id, focusBus: null, selection: new Set() });
  else setState({ focusBus: id, focusTrack: null });
  const state = getState();
  const target = kind === "bus" ? { kind, collapsed: state.collapsedBuses.has(id) } : { kind };
  const items = contextMenuItems(target, (command) => keyboard.registry.can(command, state));
  // From the keyboard (the menu key) the event has no pointer position: use the header.
  const box = event.currentTarget.getBoundingClientRect();
  const keyboardOpened = event.clientX === 0 && event.clientY === 0;
  openContextMenu({
    x: keyboardOpened ? box.left + 24 : event.clientX,
    y: keyboardOpened ? box.top + 12 : event.clientY,
    items,
    onPick: (command) => keyboard.registry.run(command, null, getState()),
    // What the item does goes in the status bar, as for the menu bar's items.
    onHint: (text) => {
      const hint = $("menu-hint");
      hint.textContent = text ?? "";
      hint.hidden = !text;
      $("keyhints").hidden = Boolean(text);
    },
  });
}
// Right-click on the timeline: a clip outside the selection is selected first, empty lane
// and the ruler put the playhead there, then the menu offers what the target allows.
function showTimelineMenu(hit, event) {
  const plan = contextPress(hit, getState());
  const patch = { panel: "timeline" };
  if (plan.selection) {
    patch.selection = plan.selection;
    patch.focusTrack = hit.row.id;
    patch.focusBus = null;
  }
  if (plan.focusTrack) {
    patch.focusTrack = plan.focusTrack;
    patch.focusBus = null;
  }
  setState(patch);
  if (plan.seek !== null) void transport.seek(plan.seek);
  const sections = timelineMenuItems(getState(), { kind: plan.kind }, (id, state) =>
    keyboard.registry.can(id, state),
  );
  const ids = sections.flatMap((section) => section.items.map((item) => item.id));
  const items = menuFromSections(sections, keyboard.describe(ids), t);
  // From the keyboard (the menu key) the event has no pointer position: use the canvas corner.
  const box = event.currentTarget.getBoundingClientRect();
  const keyboardOpened = event.clientX === 0 && event.clientY === 0;
  openContextMenu({
    x: keyboardOpened ? box.left + 24 : event.clientX,
    y: keyboardOpened ? box.top + 24 : event.clientY,
    items,
    onPick: (command) => keyboard.registry.run(command, null, getState()),
  });
}
const inspector = createInspector({
  root: $("panel-inspector"),
  editor,
  fetchMap: api.getSourceMap,
  onBusCreated: nameNewBus,
  // A row of the Source list: select that clip and move the play cursor to it.
  jump: (clip, track, frame) => {
    setState({ selection: new Set([clip]), focusTrack: track, focusBus: null, panel: "timeline" });
    void transport.seek(frame);
  },
});

// -- history (WP8) ------------------------------------------------------------------------------------

// Restore adds a step equal to an older one; the step left behind stays one Undo away.
async function restoreStep(node) {
  if (!node || node === getState().historyCurrent) return;
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
  actions: {
    restore: (node) => void restoreStep(node),
    undo: () => undo(),
    redo: () => redo(),
    showError,
  },
});

// -- markers, regions, chapters (WP19h) ------------------------------------------------------------------

// "Export all tracks" (the toolbar button, File menu, palette): one background job; the
// notice follows it (progress with Cancel, then the folder with Show in Finder). Esc cancels.
let exportJob = null;
const EXPORT_POLL_MS = 500;

async function followExportJob(id, what) {
  const bridge = globalThis.pywebview?.api;
  while (exportJob === id) {
    let job;
    try {
      job = (await api.getJobs()).jobs.find((item) => item.id === id);
    } catch (error) {
      exportJob = null;
      showError(error);
      return;
    }
    if (!job) break;
    let notice;
    if (what === "automix") notice = automixNotice(job, t);
    else if (what === "colab") notice = colabNotice(job, t, colabNames);
    else notice = exportNotice(job, t, what);
    let action = null;
    if (notice.cancel) {
      action = { label: t("ui.export.cancel"), run: () => void cancelExportJob() };
    } else if (notice.reveal && typeof bridge?.reveal_export === "function") {
      action = { label: t("ui.export.show_in_finder"), run: () => void bridge.reveal_export() };
    }
    // Done stays up (the owner reads the folder); failures and cancels time out as usual.
    showNotice(notice.text, notice.kind, { sticky: notice.sticky, action });
    if (job.state === "completed" || job.state === "failed" || job.state === "cancelled") {
      exportJob = null;
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, EXPORT_POLL_MS));
  }
}

async function cancelExportJob() {
  if (!exportJob) return;
  try {
    await api.cancelJob(exportJob);
  } catch (error) {
    showError(error);
  }
}

// `what` "tracks" or "mix"; `format` is a format id, or none for WAV (tracks) / the remembered
// one (mix). One export at a time.
async function startExport(what, format, { ask = true } = {}) {
  if (exportJob) return;
  try {
    // Desktop window: the native folder chooser first; cancelling ends here, quietly.
    const options = await exportRequest({
      format,
      ask,
      bridge: globalThis.pywebview?.api,
      hint: () => api.exportFolder(),
      // The native folder dialog has no title of its own, so say what it is for.
      onAsk: () => what === "tracks" && showNotice(t("ui.export.choose_folder"), "ok"),
    });
    if (!options) return;
    const { jobs } = await (what === "mix" ? api.exportMix(options) : api.exportTracks(options));
    exportJob = jobs[0];
    showNotice(t(`ui.export.${what}_running`, { percent: 0 }), "ok", {
      sticky: true,
      action: { label: t("ui.export.cancel"), run: () => void cancelExportJob() },
    });
    void followExportJob(exportJob, what);
  } catch (error) {
    showError(error);
  }
}
// "Mix with the automixer…" (WP68): the dialog asks, the server stems and mixes; the notice
// follows the job like an export (no percent after the stems, the tool's last line instead).
let automixDialog = null;
async function openAutomix() {
  if (exportJob) return;
  automixDialog ??= createAutomixDialog({
    api,
    t,
    onStart: async (body) => {
      try {
        const { jobs } = await api.automix(body);
        exportJob = jobs[0];
        showNotice(t("ui.automix.preparing", { percent: 0 }), "ok", {
          sticky: true,
          action: { label: t("ui.export.cancel"), run: () => void cancelExportJob() },
        });
        void followExportJob(exportJob, "automix");
      } catch (error) {
        showError(error);
      }
    },
  });
  await automixDialog.open();
}

// File > Statistics… (WP70): the server counts and words it; the dialog shows, copies, saves.
let statsDialog = null;
/** Track > Auto > Auto-Silence: close each speech mic where its owner is not talking (one undo step). */
async function autoSilence() {
  try {
    apply(await api.command("auto_silence", {}));
    showNotice(t("ui.auto_silence.done"), "ok", { undo: true });
  } catch (error) {
    showError(error);
  }
}

/** Track > Auto > Duck the microphones: write the ducking into each speech track's automation. */
async function duckMicrophones() {
  try {
    apply(await api.command("automix", {}));
    showNotice(t("ui.duck.done"), "ok", { undo: true });
  } catch (error) {
    showError(error);
  }
}

/**
 * Track > Transcribe > On this computer / On Colab: the focused track's recordings, else every
 * speech track's. Colab uploads the audio to Google, so it asks first (transcribeOnColab).
 */
async function transcribeTrack(backend = "local") {
  const state = getState();
  const track = state.project?.tracks.find((item) => item.id === state.focusTrack);
  const ids = track ? [...new Set(track.clips.map((clip) => clip.media))] : undefined;
  if (backend === "colab") await transcribeOnColab(ids ?? transcript.targetIds());
  else await transcript.transcribe(ids);
}

// Transcription is a background job in a separate process (WP79): it goes on when this window
// is closed. The window looks for what the jobs did meanwhile (a result added, a failure) every
// few seconds and once at the start, and follows a job that is still running.
const BACKGROUND_POLL_MS = 3000;
let backgroundBusy = false;

async function watchBackgroundJobs() {
  if (backgroundBusy) return;
  backgroundBusy = true;
  try {
    const { notices } = await api.jobNotices();
    for (const notice of notices) showNotice(notice.text, notice.kind);
    if (notices.some((notice) => notice.kind === "ok")) await refresh();
    if (!exportJob) {
      const running = resumableJob((await api.getJobs()).jobs);
      if (running) {
        exportJob = running.id;
        colabNames = running.title;
        void followExportJob(running.id, "colab");
      }
    }
  } catch {
    // The next look tries again; a failed look must not hide the project.
  } finally {
    backgroundBusy = false;
  }
}

// Track > Transcribe > Restart interrupted transcriptions.
async function restartTranscriptions() {
  try {
    const { restarted } = await api.restartInterrupted();
    showNotice(
      restarted.length > 0
        ? t("ui.colab.restarted", { count: restarted.length })
        : t("ui.colab.none_interrupted"),
      "ok",
    );
    void watchBackgroundJobs();
  } catch (error) {
    showError(error);
  }
}

// Transcribe on Colab (WP78): the audio leaves the computer, so the first use in a session asks
// (unless the user chose "Do not ask again", a stored preference). One job for all the
// recordings; the notice follows it like the automixer, with Cancel. The words arrive through
// the head change, like any transcript.
let colabDialogs = null;
let colabSessionOk = false;
let colabNames = "";
const colabDialogsFor = () => {
  colabDialogs ??= createColabDialogs({
    api,
    t,
    onSettingsSaved: () => showNotice(t("ui.colab.saved"), "ok"),
  });
  return colabDialogs;
};

async function transcribeOnColab(ids) {
  const project = getState().project;
  if (exportJob || !project || !ids || ids.length === 0) return;
  const names = project.media
    .filter((item) => ids.includes(item.id))
    .map((item) => item.name)
    .join(", ");
  if (consentNeeded({ remembered: rememberedConsent(prefs), session: colabSessionOk })) {
    const answer = await colabDialogsFor().askConsent(names);
    if (!answer.ok) return;
    colabSessionOk = true;
    if (answer.remember) rememberConsent(prefs);
  }
  try {
    const { jobs } = await api.transcribe(ids, { backend: "colab" });
    exportJob = jobs[0];
    colabNames = names;
    showNotice(t("ui.colab.preparing"), "ok", {
      sticky: true,
      action: { label: t("ui.export.cancel"), run: () => void cancelExportJob() },
    });
    void followExportJob(exportJob, "colab");
  } catch (error) {
    showError(error);
  }
}

// Transport > Record… (WP12a): the record view; the server owns the take, the page only shows it.
const recordView = createRecordView({
  api,
  t,
  prefs,
  getState,
  apply,
  notify: showNotice,
  chip: $("rec-chip"),
});
function cycleStopMode() {
  const mode = nextStopMode(recordView.stopMode);
  recordView.setStopMode(mode);
  showNotice(t("ui.record.stop_mode.now", { mode: t(`ui.record.stop_mode.${mode}`) }), "ok");
}

// Transport > Pre-roll (WP12c): seconds before Record that the take includes; 0 is off.
function cyclePreroll() {
  const seconds = nextPreroll(recordView.preroll);
  recordView.setPreroll(seconds);
  showNotice(t("ui.record.preroll.now", { value: prerollLabel(seconds, t) }), "ok");
}

async function openStatistics() {
  statsDialog ??= createStatsDialog({
    api,
    t,
    copyText: async (text) => {
      try {
        await navigator.clipboard.writeText(text);
        showNotice(t("ui.stats.copied"), "ok");
      } catch (error) {
        showError(error);
      }
    },
    saveJson: async () => {
      const name = await downloadFile("/api/stats?format=file", "statistics.json");
      if (name) showNotice(t("ui.stats.saved", { name }), "ok");
    },
  });
  await statsDialog.open();
}

// File > Locate media… (WP39) and File > Send a copy… (WP32). The desktop window has a native
// folder chooser; a plain browser types the folder.
const folderChooser = () =>
  typeof globalThis.pywebview?.api?.pick_project_folder === "function"
    ? () => globalThis.pywebview.api.pick_project_folder()
    : null;
let locateDialog = null;
async function openLocateMedia() {
  locateDialog ??= createLocateDialog({
    api,
    t,
    pickFolder: folderChooser(),
    onChanged: () => void refresh().catch(showError),
  });
  await locateDialog.open();
}
let sendCopyDialog = null;
async function openSendCopy() {
  sendCopyDialog ??= createSendCopyDialog({
    api,
    t,
    pickFolder: folderChooser(),
    onDone: (report) => showNotice(t("ui.send_copy.done", { path: report.path }), "ok"),
  });
  await sendCopyDialog.open();
}
/** A project that opens with audio files missing says so once, with one click to locate them. */
function offerToLocate(missing) {
  const notice = missingNotice(missing);
  if (!notice) return;
  showNotice(t(notice.key, notice.values), "ok", {
    sticky: true,
    action: {
      label: t("ui.locate.notice_action"),
      run: () => {
        $("notice").hidden = true;
        void openLocateMedia();
      },
    },
  });
}

const exportTracks = (format, options) => startExport("tracks", format, options);
const exportMix = (format, options) => startExport("mix", format, options);

// File > Export mix (options)… / Export all tracks (options)… (WP74): format, and whether to
// choose the folder first (only the desktop window has a folder chooser).
let exportDialog = null;
function openExportDialog(what) {
  exportDialog ??= createExportDialog({
    t,
    formats: () => exportFormatList,
    canChooseFolder: () => typeof globalThis.pywebview?.api?.choose_export_folder === "function",
    onStart: ({ what: kind, format, ask }) =>
      kind === "mix" ? exportMix(format, { ask }) : exportTracks(format, { ask }),
  });
  exportDialog.open(what);
}

// File > New project… / Open project… (WP74). The desktop window uses its native dialogs and
// opens the project in a window of its own; a plain browser asks for a path in a small dialog
// and the server opens the project in a new tab.
let projectDialog = null;
function askProjectPath(kind) {
  projectDialog ??= createProjectDialog({
    api,
    t,
    onDone: (path) => showNotice(t("ui.project.opened", { path }), "ok", { undo: false }),
  });
  projectDialog.open(kind);
}
async function newProject() {
  const bridge = globalThis.pywebview?.api;
  if (typeof bridge?.new_project_in_window !== "function") return askProjectPath("new");
  try {
    await bridge.new_project_in_window();
  } catch (error) {
    showError(error);
  }
}
async function openProject() {
  const bridge = globalThis.pywebview?.api;
  if (typeof bridge?.open_project_in_window !== "function") return askProjectPath("open");
  try {
    await bridge.open_project_in_window();
  } catch (error) {
    showError(error);
  }
}

// The formats the server can write (ids, in its order); asked for once, at start.
api
  .exportFormats()
  .then((formats) => {
    exportFormatIds = formats.map((format) => format.id);
    exportFormatList = formats;
  })
  .catch(() => {});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && exportJob) void cancelExportJob();
});

// One background job renders every region to its own file; the jobs list shows progress.
async function exportRegions() {
  const count = regionCount(getState().project?.markers);
  try {
    await api.exportRegions();
    showNotice(t("ui.markers.regions_queued", { count }), "ok");
  } catch (error) {
    showError(error);
  }
}

function sendMarkerEdit(op, args, labelKey) {
  editor.change({ op, args, label: t(labelKey) });
}

// -- clipboard (WP46) -----------------------------------------------------------------------------------

async function refreshClipboard() {
  try {
    setState({ clipboard: (await api.getClipboard()).entries });
  } catch (error) {
    showError(error);
  }
  void loadSharedClipboard();
}

// -- clipboard sharing and other projects (WP65) --------------------------------------------------

async function loadSharedClipboard() {
  try {
    setState({ clipboardShared: (await api.getClipboardShared()).entries });
  } catch (error) {
    showError(error);
  }
}

// The recent projects, with the ones picked by hand in front. The counts are read by the
// server each time, so they are not stale.
async function loadClipboardProjects() {
  try {
    const recent = (await api.getClipboardProjects()).projects;
    const opened = getState().clipboardOpened ?? [];
    const known = new Set(opened.map((project) => project.path));
    setState({ clipboardProjects: [...opened, ...recent.filter((p) => !known.has(p.path))] });
  } catch (error) {
    showError(error);
  }
}

function setForeign(path, value) {
  setState({ clipboardForeign: { ...(getState().clipboardForeign ?? {}), [path]: value } });
}

async function loadForeignClipboard(path) {
  setForeign(path, { status: "loading", entries: [] });
  try {
    const answer = await api.getClipboardProject(path);
    setForeign(path, { status: "ok", entries: answer.entries });
    return answer;
  } catch (error) {
    setForeign(path, { status: "error", entries: [] });
    showError(error);
    return null;
  }
}

function setClipboardView(view) {
  setState({ clipboardView: view });
  if (view === "shared") void loadSharedClipboard();
  if (view === "others") void loadClipboardProjects();
}

function showClipboard(view) {
  focusPanel("clipboard");
  setClipboardView(view);
}

function toggleClipboardProject(path) {
  const open = getState().clipboardExpanded ?? [];
  if (open.includes(path)) {
    setState({ clipboardExpanded: open.filter((item) => item !== path) });
    return;
  }
  setState({ clipboardExpanded: [...open, path] });
  void loadForeignClipboard(path);
}

// Any project's clipboard, read-only: the desktop picks the folder natively; a browser types it.
const clipboardPicker = () =>
  typeof globalThis.pywebview?.api?.pick_project_folder === "function"
    ? globalThis.pywebview.api
    : null;

async function openClipboardProjectAt(path) {
  const answer = await loadForeignClipboard(path);
  if (!answer) return;
  const project = {
    name: answer.project.name,
    path: answer.project.path,
    last_opened: "",
    entries: answer.entries.length,
  };
  const opened = [
    project,
    ...(getState().clipboardOpened ?? []).filter((p) => p.path !== project.path),
  ];
  const expanded = getState().clipboardExpanded ?? [];
  // The server resolved the path (links, trailing slash): list and expand it under that name.
  if (project.path !== path) setForeign(project.path, { status: "ok", entries: answer.entries });
  setState({
    clipboardOpened: opened,
    clipboardExpanded: expanded.includes(project.path) ? expanded : [...expanded, project.path],
  });
  void loadClipboardProjects();
}

async function openClipboardProject() {
  showClipboard("others");
  const picker = clipboardPicker();
  if (!picker) {
    queueMicrotask(() => $("panel-clipboard").querySelector(".clip-path")?.focus());
    return;
  }
  try {
    const path = await picker.pick_project_folder();
    if (path) await openClipboardProjectAt(path);
  } catch (error) {
    showError(error);
  }
}

async function shareClipboardEntry(id, on) {
  try {
    const answer = await api.shareClipboardEntry(id, on);
    setState({ clipboard: answer.entries, clipboardShared: answer.shared });
    showNotice(t(on ? "ui.clipboard.shared" : "ui.clipboard.unshared"), "ok", { undo: false });
  } catch (error) {
    showError(error);
  }
}

// Copy an entry of the shared store or another project into this project's clipboard. It becomes
// the newest entry and is picked, so the paste keys paste it. Returns whether it worked.
async function adoptClipboardEntry(entry, from, { quiet = false } = {}) {
  try {
    const answer = await api.adoptClipboardEntry(entry, from);
    setState({ clipboard: answer.entries, clipboardSelected: answer.entry.id });
    if (!quiet) {
      showNotice(t("ui.clipboard.adopted", { name: entryTitle(answer.entry, rateOf(), t) }), "ok", {
        undo: false,
      });
    }
    return true;
  } catch (error) {
    showError(error);
    return false;
  }
}

const rateOf = () => getState().project?.rate ?? 48000;

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

// "Clear old entries": keep the newest `keep` of this project's, say how many went.
async function clearOldClipboard(keep) {
  try {
    const answer = await api.clearOldClipboard(keep);
    setState({ clipboard: answer.entries, clipboardSelected: null });
    showNotice(
      answer.removed > 0
        ? t("ui.clipboard.cleared", { count: answer.removed })
        : t("ui.clipboard.cleared_none"),
      "ok",
      { undo: false },
    );
    return answer.removed;
  } catch (error) {
    showError(error);
    return 0;
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
    rename: (id, name) => void clipboardAction(() => api.renameClipboardEntry(id, name))(),
    remove: (id) => {
      if (getState().clipboardSelected === id) setState({ clipboardSelected: null });
      void clipboardAction(() => api.deleteClipboardEntry(id))();
    },
    choose: (patch) => setState(patch),
    filter: (text) => setState({ clipboardFilter: text }),
    share: (id, on) => void shareClipboardEntry(id, on),
    view: (name) => setClipboardView(name),
    toggleProject: (path) => toggleClipboardProject(path),
    openProject: () => keyboard.registry.run("clipboard.open_project", null, getState()),
    openPath: (path) => void openClipboardProjectAt(path),
    hasPicker: () => clipboardPicker() !== null,
    now: () => Date.now() / 1000,
    adopt: (entry, from) => void adoptClipboardEntry(entry, from),
    async pasteHere(entry, from) {
      if (await adoptClipboardEntry(entry, from, { quiet: true })) {
        keyboard.registry.run(pasteCommand(getState()), null, getState());
      }
    },
    keep: (value) => setState({ clipboardKeep: Number(value) }),
    clearOld: () => keyboard.registry.run("edit.clear_old_clipboard", null, getState()),
    preview(id) {
      setState({ clipboardSelected: id });
      keyboard.registry.run("edit.preview_clipboard", null, getState());
    },
    canPasteAgain: (state) => keyboard.registry.can(pasteCommand(state), state),
    pasteAgain(id) {
      setState({ clipboardSelected: id });
      keyboard.registry.run(pasteCommand(getState()), null, getState());
    },
  },
});
const markersPanel = createMarkersPanel({
  root: $("panel-markers"),
  actions: {
    jumpLeftOff: () => keyboard.registry.run("nav.to_resume", null, getState()),
    jump(id) {
      const marker = getState().project?.markers?.find((item) => item.id === id);
      if (!marker) return;
      setState({ markerSelected: id });
      void transport.seek(marker.start);
    },
    rename: (id, name) =>
      sendMarkerEdit("rename_marker", { marker_id: id, name }, "ui.markers.history.rename"),
    setKind: (id, kind) =>
      sendMarkerEdit("set_marker_kind", { marker_id: id, kind }, "ui.markers.history.kind"),
    remove(id) {
      setState({ markerSelected: id });
      keyboard.registry.run("marker.delete", null, getState());
    },
    jumpClip(clipId, start) {
      setState({ selection: new Set([clipId]) });
      void transport.seek(start);
    },
    syncCause: (clipId) => api.getSyncCause(clipId).then((answer) => answer.cause),
    can: (id, state) => keyboard.registry.can(id, state),
    run: (id) => keyboard.registry.run(id, null, getState()),
  },
});

// Another window of kuulas may have copied something: look again when this one is back.
window.addEventListener("focus", () => void refreshClipboard());

// -- cut candidates (WP18) ------------------------------------------------------------------------------

let candidatesToken = 0;

/** Fetch the list again (the newest answer wins). The frames move with every edit, so this
 * runs whenever the head changes, not only while the tab is showing: the timeline draws them. */
async function refreshCandidates() {
  const mine = ++candidatesToken;
  try {
    const answer = await api.getCandidates();
    if (mine === candidatesToken) {
      setState({ candidates: answer.candidates, candidateSummary: answer.summary });
    }
    return answer;
  } catch (error) {
    if (mine === candidatesToken) showError(error);
    return null;
  }
}

// A row picked (click, Alt+Down/Up or the arrows): the play cursor goes to its start, the timeline
// scrolls so it shows, and the preview bar's numbers are fetched.
function selectCandidate(row) {
  const state = getState();
  const patch = { candidateCurrent: row.id, candidatePreview: null };
  if (row.start !== null) {
    patch.scroll = View.clampScroll(
      scrollToShow(row.start, { scroll: state.scroll, zoom: state.zoom, width: width() }),
      state.zoom,
      width(),
      totalFrames(),
    );
  }
  setState(patch);
  if (row.start === null) return;
  void transport.seek(row.start);
  api
    .getCandidatePreview(row.id)
    .then((data) => {
      if (getState().candidateCurrent === row.id) {
        setState({ candidatePreview: { id: row.id, ...data } });
      }
    })
    .catch(showError);
}

async function findCandidates() {
  const before = new Set(getState().candidates.map((row) => row.id));
  setState({ candidateBusy: true, candidateFound: null });
  try {
    apply(await api.command("candidates_detect", {}));
    const answer = await refreshCandidates();
    const after = new Set((answer?.candidates ?? []).map((row) => row.id));
    setState({
      candidateFound: {
        added: [...after].filter((id) => !before.has(id)).length,
        dropped: [...before].filter((id) => !after.has(id)).length,
      },
    });
  } catch (error) {
    showError(error);
  } finally {
    setState({ candidateBusy: false });
  }
}

// After a decision the next open candidate becomes the current one: the second listen is
// then Enter, Enter, K, Enter.
async function afterDecision() {
  // The answer itself, not the state: a newer refresh (the live channel's) may still be
  // in flight and the state then still lists the candidate just decided as open.
  const answer = await refreshCandidates();
  if (!answer) return;
  const next = stepTarget(
    listedRows(answer.candidates, true),
    { currentId: null, playhead: getState().playhead - 1 },
    1,
  );
  if (next) selectCandidate(next);
}

async function applyCandidate(id, mode) {
  try {
    apply(await api.command("candidate_apply", { id, mode }));
    showNotice(t(mode === "soft" ? "ui.candidates.deleted" : "ui.candidates.cut"), "ok", {
      undo: true,
    });
    await afterDecision();
  } catch (error) {
    showError(error);
  }
}

async function keepCandidate(id) {
  try {
    apply(await api.command("candidate_set_state", { id, state: "kept" }));
    showNotice(t("ui.candidates.kept"), "ok", { undo: true });
    await afterDecision();
  } catch (error) {
    showError(error);
  }
}

async function markCandidate(start, end, track) {
  try {
    apply(await api.command("candidate_mark", { start, end, track_id: track }));
    showNotice(t("ui.candidates.marked"), "ok", { undo: true });
    await refreshCandidates();
  } catch (error) {
    showError(error);
  }
}

// Preview: one play request; the engine skips the candidate with a crossfade
// (candidates-preview.js). The project is not touched.
async function previewCandidate(row) {
  try {
    const request = previewRequest(await api.getCandidatePreview(row.id));
    if (!request) return;
    showNotice(t("ui.candidates.preview_running"), "ok");
    await transport.preview(request.at, request.until, request.skip);
  } catch (error) {
    showError(error);
  }
}

const candidatesPanel = createCandidatesPanel({
  root: $("panel-candidates"),
  getState,
  actions: {
    select: (row) => selectCandidate(row),
    find: () => keyboard.registry.run("candidate.find", null, getState()),
    toggleOpenOnly: () => keyboard.registry.run("candidate.filter", null, getState()),
    can: (id, state) => keyboard.registry.can(id, state),
    run: (id) => keyboard.registry.run(id, null, getState()),
  },
});

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
    seek: (frame) => void transport.seek(frame),
    contextMenu: (hit, event) => showTimelineMenu(hit, event),
    rangeDragged: onRangeDragged,
    clipDrag({ ids, move, alone = false }) {
      // Alt held: this clip moves alone, whatever group editing says, and then asks whether it
      // should stay free from sync (owner, 2026-10-16).
      const change = clipDragChange(ids, move, getState().groupEditing !== false && !alone);
      if (!change) return;
      setState({ selection: new Set(ids) }); // the press selected one clip; a move keeps all
      editor.change({
        op: change.op,
        args: change.args,
        label: t(change.labelKey),
        done: alone ? () => void askToFree(ids) : undefined,
      });
    },
    clipGain({ clipId, gain }) {
      const { op, args, coalesce, labelKey } = gainChange(clipId, gain);
      editor.change({
        op,
        args,
        coalesce,
        label: t(labelKey),
        provisional: (p) => patchClip(p, clipId, { gain_db: gain }),
      });
    },
    clipFade({ clipId, side, frames }) {
      const { op, args, coalesce, labelKey } = fadeChange(clipId, side, frames);
      editor.change({
        op,
        args,
        coalesce,
        label: t(labelKey),
        provisional: (p) => patchClip(p, clipId, { [`fade_${side}`]: frames }),
      });
    },
    edgeDrag({ clipId, edge, frame, ripple }) {
      const { op, args, labelKey } = edgeChange(
        clipId,
        edge,
        frame,
        ripple,
        getState().groupEditing !== false,
      );
      editor.change({ op, args, label: t(labelKey) });
    },
    openGate: openGateStretch,
    editPlaceholder(placeholder) {
      setState({ placeholderSelected: placeholder.id });
      keyboard.registry.run("placeholder.edit", null, getState());
    },
    wheel: onWheel,
    resized() {
      if (fitWhole && getState().project) fitWholeEdit();
      autoFit(getState());
      updateLanesScroll(getState());
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

// The Alku / Loppu / Pituus readout in the transport corner.
const marksCorner = createMarksCorner({
  root: document.querySelector(".rcol"),
  getState,
  rate,
  format: frameToTime,
  limit: totalFrames,
  run: (id) => keyboard.registry.run(id, null, getState()),
  patch: setState,
  copy: (text) => void clock.copy(text),
  t,
});

// The big play-cursor time: click copies it, double-click (or Spot, Cmd+J) types a time to jump to.
const clock = createClock({
  el: $("timecode"),
  getState,
  rate,
  limit: totalFrames,
  format: frameToTime,
  seek: (frame) => void transport.seek(frame),
  notify: showNotice,
  t,
});

// -- render -----------------------------------------------------------------------------------------------

function spanText(state) {
  const info = View.describeZoom(state.zoom, viewLevels(), { width: width(), rate: rate() });
  if (info.kind === "whole") return t("ui.zoom.whole");
  if (info.kind === "samples") return t("ui.zoom.samples");
  const { unit, value } = View.spanParts(info.seconds);
  return t(`ui.zoom.${unit}`, { value: formatNumber(value, { digits: GAIN_DIGITS(value) }) });
}

// "2 clips · 12:03,250-12:41,000 · 0:37,750": the selected clips (the marks are in the corner).
function updateRangeInfo() {
  const el = $("range-info");
  const state = getState();
  const text = rangeLine(state, rate(), frameToTime, t);
  el.hidden = text === null;
  if (text !== null) el.textContent = text;
}
let lastLoopKey = "null";

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
      "laneHeights",
      "collapsedBuses",
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
    const time = frameToTime(state.playhead, rate());
    clock.render(time);
    // The hour form is wider, so the corner sets it smaller.
    $("timecode").classList.toggle("hour", time.split(":").length > 2);
  }
  if (touched("project", "selection", "inPoint", "outPoint")) updateRangeInfo();
  if (touched("project", "inPoint", "outPoint")) marksCorner.render(state);
  if (touched("project", "words")) updateTabScope();
  if (touched("playing")) {
    levelMeter.playing(state.playing);
    $("play-icon").textContent = state.playing ? "■" : "▶";
    $("play-label").textContent = t(state.playing ? "ui.transport.stop" : "ui.transport.play");
  }
  if (touched("loop", "project", "inPoint", "outPoint", "selection")) {
    const button = $("loop");
    button.setAttribute("aria-pressed", String(state.loop));
    button.disabled = !keyboard.registry.can("transport.loop", state);
    button.title = t(state.loop ? "ui.transport.loop_on" : "ui.transport.loop");
    // A new range or a switch while playing goes to the engine without stopping.
    const loopKey = JSON.stringify(activeLoop(state));
    if (loopKey !== lastLoopKey) {
      lastLoopKey = loopKey;
      if (state.playing) void transport.resendLoop();
    }
  }
  if (touched("speed", "playing", "fast")) {
    const chip = $("speed-chip");
    // Fast listening on shows its exact speed even while stopped (nobody should edit at
    // 1.35x by mistake); otherwise a shuttle speed while it plays.
    const fastLabel = chipFast(state.fast, formatNumber);
    const label = fastLabel ?? chipSpeed(state.speed, state.playing, formatNumber);
    chip.hidden = label === null;
    if (label !== null) chip.textContent = t("ui.speed.chip", { speed: label });
    chip.title = t(fastLabel === null ? "ui.speed.chip_title" : "ui.speed.fast_chip_title");
    chip.classList.toggle("draggable", fastLabel !== null);
    const slider = $("fast-speed");
    if (Number(slider.value) !== state.fast.fast) slider.value = String(state.fast.fast);
    slider.setAttribute(
      "aria-valuetext",
      t("ui.speed.chip", { speed: formatNumber(state.fast.fast, { digits: 2 }) }),
    );
    slider.classList.toggle("on", state.fast.active);
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
  if (
    touched(
      "project",
      "focusTrack",
      "focusBus",
      "laneHeight",
      "laneHeights",
      "collapsedBuses",
      "busHeight",
      "groupGap",
      "loudness",
    )
  )
    trackHeaders.update(state);
  if (touched("project", "autoFitTracks", "laneHeights", "collapsedBuses", "busHeight", "groupGap"))
    autoFit(state);
  if (
    touched(
      "project",
      "scrollY",
      "laneHeight",
      "laneHeights",
      "collapsedBuses",
      "busHeight",
      "groupGap",
    )
  )
    updateLanesScroll(state);
  if (touched("project", "selection", "focusTrack", "focusBus")) inspector.update(state);
  if (touched("selection", "focusTrack", "focusBus", "panel")) help.update();
  if (
    touched(
      "clipboard",
      "clipboardSelected",
      "clipboardFilter",
      "clipboardKeep",
      "clipboardView",
      "clipboardShared",
      "clipboardProjects",
      "clipboardForeign",
      "clipboardExpanded",
      "pasteMode",
      "pasteTarget",
      "project",
      "focusTrack",
      "playhead",
    )
  )
    clipboardPanel.update(state);
  if (touched("project", "markerSelected", "playhead", "inPoint", "outPoint", "syncClips"))
    markersPanel.update(state);
  if (state.head && touched("head")) void refreshCandidates();
  if (state.head && touched("head")) void refreshSync();
  // Partners are asked for after an edit lands (head), not at every provisional step of a drag.
  if (touched("head") && Object.keys(state.partners).length > 0) setState({ partners: {} });
  if (touched("selection", "partners", "head") && state.project?.sync_groups?.length > 0)
    void refreshPartners();
  if (touched("groupEditing")) void api.setGroupEditing(state.groupEditing).catch(() => {});
  if (touched("head") && rangeMemory) {
    const step = stepRangeMemory(rangeMemory, state.head, state);
    rangeMemory = step.memory;
    if (step.patch) setState(step.patch);
  }
  if (
    touched(
      "candidates",
      "candidateSummary",
      "candidateCurrent",
      "candidatesOpenOnly",
      "candidateBusy",
      "candidateFound",
      "candidatePreview",
      "project",
    )
  )
    candidatesPanel.update(state);
  if (touched("candidateSummary")) {
    const open = state.candidateSummary?.open ?? 0;
    $("cand-count").hidden = open === 0;
    $("cand-count").textContent = String(open);
  }
  if (touched("sidebarTab")) {
    for (const name of SIDEBAR_TABS) {
      $(`panel-${name}`).hidden = state.sidebarTab !== name;
      $(`tab-${name}`).setAttribute("aria-selected", String(state.sidebarTab === name));
      $(`tab-${name}`).tabIndex = state.sidebarTab === name ? 0 : -1;
    }
  }
  if (touched("head", "sidebarTab", "historySelected", "canUndo", "canRedo"))
    historyPanel.update(state);
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
  if (touched("playhead", "playing", "zoom", "scroll", "followMode", "followPaused"))
    follow(state, touched("playhead"));
  transcript.update(state, patch);
}

// While playing, keep the playhead in view (page or continuous) unless the user
// scrolled away by hand.
function follow(state, moved = false) {
  const next = followScroll({
    moved,
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

// The live level meter in the status bar: drawn from the live channel's frames, outside the
// store (about 15 frames a second must not re-render the editor).
const levelMeter = createLevelMeter({
  root: $("level-meter"),
  bars: $("level-bars"),
  clipButton: $("level-clip"),
});
subscribe(render);

// The loudness readout in the track headers: asked in the background once the project has
// settled (loudness-readout.js), never blocking an edit.
const loudnessLoader = createLoudnessLoader({
  fetchCurve: (signal) => api.getLoudnessCurve(signal),
  onChange: (patch) => setState(patch),
});
subscribe(() => loudnessLoader.settle(getState().project ? getState().head : null));
onLanguageChange(() => {
  importPanel.refresh();
  translate();
  applyTheme();
  render(getState(), null);
});

// -- view memory (WP35) -----------------------------------------------------------------
// Zoom, scroll, tab, cursor and marks come back when the project is opened again. The
// record lives in a per-user file on the server, never in the project (no undo step).
// Saving starts only after the restore, or the defaults would overwrite what was kept.

const currentRecord = () => recordOf(getState(), { whole: fitWhole });
const viewSaver = createSaver({ save: (record, options) => api.putViewMemory(record, options) });
let viewMemoryOn = false;
let lastViewKey = "";

function scheduleViewSave(state) {
  if (!viewMemoryOn || !state.project) return;
  const key = changeKey(state, { whole: fitWhole, now: Date.now() });
  if (key === lastViewKey) return;
  lastViewKey = key;
  viewSaver.touch(currentRecord);
}

/** What leftOffText needs from the UI: translation, clock format, language. */
const leftOffWords = () => ({
  t,
  clock: (seconds) => formatClock(seconds),
  language: getLanguage(),
});

async function restoreView() {
  try {
    const { view } = await api.getViewMemory();
    const { patch, whole } = restoreFrom(view, {
      project: getState().project,
      width: width(),
      totalFrames: totalFrames(),
    });
    if (patch.zoom !== undefined) {
      setView({ zoom: patch.zoom, scroll: patch.scroll ?? 0 }, { record: false, whole });
      if (whole) fitWholeEdit();
    }
    delete patch.zoom; // applied by setView, with its scroll
    delete patch.scroll;
    setState(patch);
    if (patch.playhead) void transport.seek(patch.playhead);
    // "Back where you left off": the automatic marker, and a notice for a few seconds.
    const leftOff = leftOffOf(view, totalFrames());
    setState({ leftOff });
    if (leftOff) {
      const rate = getState().project?.rate ?? 48000;
      showNotice(leftOffText(leftOff, rate, leftOffWords(), "notice"), "ok");
    }
  } catch (error) {
    // Nothing remembered, or the server is not reachable: start with the defaults.
    console.warn("the remembered view could not be restored", error);
  }
  viewMemoryOn = true;
  lastViewKey = changeKey(getState(), { whole: fitWhole });
  subscribe(scheduleViewSave);
}

// Leaving the page: write what is pending now (the debounce would be lost with the page).
// The latest record is sent (not just what is pending), also while playing, when the cursor
// moves without a save being queued, and the server then writes resume.json at once. A
// desktop window may fire none of these; desktop.py flushes the position on close.
function flushView() {
  if (viewMemoryOn && getState().project) viewSaver.flush(currentRecord);
}
addEventListener("beforeunload", flushView);
addEventListener("pagehide", flushView);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") flushView();
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

// Which build is this: the label goes in the status bar so a bug report names it.
api
  .getBuild()
  .then(({ build }) => {
    $("build-label").textContent = build;
  })
  .catch(() => {});

try {
  const [state, words] = await Promise.all([api.getState(), api.getWords()]);
  apply(state);
  offerToLocate(state.missing);
  setState({ words: words.words ?? [], wordsHead: getState().head });
  await restoreView();
  await refreshClipboard();
} catch (error) {
  showError(error);
}
void watchBackgroundJobs();
setInterval(() => void watchBackgroundJobs(), BACKGROUND_POLL_MS);
// A take running for this project shows the record view again; takes a crash left behind
// are offered with one click (never imported by themselves).
void recordView.start();

let handledNotice = 0;
let wasDown = false;
connectLive({
  url: api.liveUrl(),
  onStatus(status) {
    setState({ live: status });
    if (status === "open" && wasDown) {
      // Whatever happened while the connection was gone: fetch it again.
      void refresh().catch(showError);
      void recordView.refresh();
      void api
        .getTransport()
        .then((s) => setState({ playing: s.playing, playhead: s.position }))
        .catch(showError);
    }
    wasDown = status === "reconnecting";
  },
  onMessage(message) {
    if (message.type === "record") {
      recordView.live(message);
      return;
    }
    const result = reduceLive(getState(), message);
    if (Object.keys(result.patch).length > 0) setState(result.patch);
    // An answer to our own edit arrives as a state_changed too; while edits are
    // still going out, the editor shows the newest value and applies the last answer.
    if (result.meter) levelMeter.frame(result.meter);
    if (result.clipboard) void refreshClipboard();
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
