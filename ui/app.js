// The editor's entry point: wires the store, the API, the live channel, the
// canvases and the keyboard together. The decisions live in small pure modules
// (view.js, lanes.js, keys.js, ...); this file only applies their answers.

import * as api from "./api.js";
import { SIDE_TAB_COMMANDS } from "./app-commands.js";
import { createAutomixDialog } from "./automix-dialog.js";
import { createAutomixLiveDialog } from "./automix-live-dialog.js";
import { createAutomixToast } from "./automix-toast.js";
import { automixToast } from "./automix-toast-model.js";
import { createBlockLevelDialog } from "./block-level-dialog.js";
import { memberClipsAt, toggleChange } from "./bus-collapse.js";
import { trackRoleChoice } from "./bus-role.js";
import { listedRows, scrollToShow, stepTarget } from "./candidates-model.js";
import { createCandidatesPanel } from "./candidates-panel.js";
import { previewRequest } from "./candidates-preview.js";
import { clipDragChange } from "./clip-drag.js";
import { expandGroups, toggleGroupSelection } from "./clip-groups.js";
import { entryTitle } from "./clipboard.js";
import { createClipboardDrag } from "./clipboard-drag.js";
import { createClipboardPanel } from "./clipboard-panel.js";
import { previewFraction, previewPlaying, previewStop } from "./clipboard-preview.js";
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
import { installDialogKeys } from "./dialog-keys.js";
import { dragModeChoice, nextDragMode } from "./drag-mode.js";
import { createDuckMusicDialog } from "./duck-music-dialog.js";
import {
  DEFAULTS as DUCK_MUSIC_DEFAULTS,
  normaliseSettings as normaliseDuckMusic,
} from "./duck-sidechain-model.js";
import { edgeChange, edgePressKeepsSelection } from "./edge-drag.js";
import { dropPastePlan } from "./edit-plans.js";
import { createEditor } from "./edits.js";
import { createNewEpisodeDialog } from "./episode-dialog.js";
import { escapeAction } from "./escape.js";
import { exportNotice, exportRequest, filenameFromDisposition } from "./export-commands.js";
import { createExportDialog } from "./export-dialog.js";
import { quickPlan } from "./export-dialog-model.js";
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
import {
  focusHeights,
  focusResizeMs,
  followCurrent,
  soloSteps,
  startFocus,
  stopFocus,
  tweenHeights,
} from "./focus-layout.js";
import { followScroll } from "./follow.js";
import { frameToTime, RATE, xToFrame } from "./format.js";
import { envelopeChange, fadeChange, gainChange } from "./gain-drag.js";
import { GATE_OPEN_COMMAND, openStretchEdit, stretchAt, underClipsEdit } from "./gate.js";
import { HELP_COMMAND, shortcutsFor } from "./help.js";
import { createHelpPanel } from "./help-panel.js";
import { undoNotice } from "./history-model.js";
import { createHistoryPanel } from "./history-panel.js";
import {
  detectLanguage,
  formatAbsoluteTime,
  formatClock,
  formatNumber,
  formatShortcut,
  getLanguage,
  initI18n,
  onLanguageChange,
  setLanguage,
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
import { createMusicLevelDialog } from "./music-level-dialog.js";
import { MUSIC_UNDER_KEY, normaliseMusicUnder } from "./music-level-model.js";
import { createOverview } from "./overview.js";
import { createPerfDialog } from "./perf-dialog.js";
import { createPlaceholderEditor } from "./placeholder-editor.js";
import { createPlayheadClock } from "./playhead-clock.js";
import { createPreferencesDialog } from "./preferences-dialog.js";
import { loadPrefs } from "./prefs.js";
import { nextPreroll, prerollLabel } from "./preroll.js";
import { createProjectDialog } from "./project-dialog.js";
import { patchClip } from "./provisional.js";
import { normaliseQuickMute, QUICK_MUTE_KEY } from "./quick-mute.js";
import { rangeLine } from "./range-info.js";
import { rememberRange, stepRangeMemory } from "./range-memory.js";
import {
  clearTrackSelection,
  focusTrack as focusTrackPatch,
  laneClickFocus,
  resolveScope,
  scopeChip,
  toggleScopeMode,
} from "./range-scope.js";
import { recentMenuItems } from "./recent-menu-model.js";
import { createRecordView } from "./record-view.js";
import { createRelinkConfirm, relinkPlan } from "./relink-media.js";
import { rangeChoice, renderWhen } from "./render-listen-model.js";
import { createRenderListenView } from "./render-listen-view.js";
import { forwardFromClip } from "./selection-ops.js";
import { createSendCopyDialog } from "./send-copy-dialog.js";
import { createSeriesDialog } from "./series-dialog.js";
import { seriesChip } from "./series-model.js";
import { adoptRequest, createSeriesShelf } from "./series-shelf.js";
import { setupKeyboard } from "./shell-keys.js";
import { chipSpeed } from "./shuttle.js";
import { keyHint, tabMode, tabTitle } from "./side-tabs-model.js";
import { SIDEBAR_KEY, sidebarPref, sidebarShown, toggleSidebar } from "./sidebar-model.js";
import { normaliseSilence } from "./silence-model.js";
import { createSilencePanel } from "./silence-panel.js";
import { inactiveStyleChoice } from "./silence-visuals.js";
import { createSlowHold, normaliseSlow, slowSpeed } from "./slow-hold.js";
import { createStatsDialog } from "./stats-dialog.js";
import { nextStopMode } from "./stop-mode.js";
import { anchorPatch, getState, reduceLive, serverPatch, setState, subscribe } from "./store.js";
import { createSyncConfirm } from "./sync-confirm.js";
import { driftingAmong } from "./sync-state.js";
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
import { withoutMusic } from "./transcribable.js";
import { createTranscript } from "./transcript.js";
import { mutedInputsKey, pauseChoiceId } from "./transcript-model.js";
import { createTransport } from "./transport.js";
import * as View from "./view.js";
import { changeKey, createSaver, recordOf, restoreFrom } from "./view-memory.js";
import { nextWheelMode, wheelModeChoice } from "./wheel.js";

const $ = (id) => document.getElementById(id);
installIcons();
// The Auto-Silence live preview panel (openSilenceOptions): made on first use; declared here
// because render() asks it about every project change from the first render on.
let silencePanel = null;
const prefs = await loadPrefs(); // server-side store, read once before the first prefs.get
const WAVEFORM_GAIN = { min: 1 / 8, max: 32, snap: 0.04 };
const LANE_STEP = 8;
const SETTLE_MS = 160;
const NOTICE_MS = { error: 9000, ok: 4000 };
const GAIN_DIGITS = (value) => (Number.isInteger(value) ? 0 : 1);

// -- text -------------------------------------------------------------------

// Each side tab: tooltip "Name (Alt+n)", aria-keyshortcuts, the digit for the compact strip, and
// the step (full / tight / compact) that keeps the strip on one row.
let tabKeyEntries = null;
function applyTabs() {
  const platform = detectPlatform();
  for (const [id, tab] of Object.entries(SIDE_TAB_COMMANDS)) {
    const button = $(`tab-${tab}`);
    const name = t(`ui.tabs.${tab}`);
    const combos = tabKeyEntries ? shortcutsFor(id, tabKeyEntries) : [];
    const shown = combos.map((combo) => formatCombo(combo, platform));
    button.title = tabTitle(name, shown);
    button.setAttribute("aria-label", name);
    button.setAttribute(
      "aria-keyshortcuts",
      combos.map((c) => c.replace(/\bMod\b/, platform === "mac" ? "Meta" : "Control")).join(" "),
    );
    const key = button.querySelector(".tab-key");
    key.dataset.full = shown[0] ?? "";
    key.dataset.short = keyHint(shown[0]);
  }
  layoutTabs();
}

/** Pick the strip's step from what each step needs (measured) and the room it has. */
function layoutTabs() {
  const strip = document.querySelector(".side-tabs");
  if (!strip || strip.clientWidth === 0) return;
  const style = getComputedStyle(strip);
  const gap = Number.parseFloat(style.columnGap) || 0;
  const pad = Number.parseFloat(style.paddingLeft) + Number.parseFloat(style.paddingRight);
  const kids = [...strip.children];
  const measure = (mode) => {
    strip.dataset.tabs = mode;
    return kids.reduce((sum, kid) => sum + kid.offsetWidth, 0) + gap * (kids.length - 1) + pad;
  };
  const needed = { full: measure("full"), tight: measure("tight") };
  strip.dataset.tabs = tabMode(needed, strip.clientWidth);
}
new ResizeObserver(layoutTabs).observe(document.querySelector(".side-tabs"));

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
  applyTabs();
}

let noticeTimer = null;
// `undo`: the message offers an Undo button (the edit keys' toast).
// `sticky`: it stays until replaced or closed (a running export). `action`: { label, run }
// shows one more button (Cancel, Show in Finder); `action2` a second one (Show log).
let noticeAction = null;
let noticeAction2 = null;
// `rich`: the running automixer's structured view (automix-toast-model.js); `text` stays
// the plain line under it.
const richToast = createAutomixToast();
function showNotice(
  text,
  kind = "error",
  { undo = false, sticky = false, action = null, action2 = null, rich = null } = {},
) {
  const notice = $("notice");
  $("notice-text").textContent = text;
  if (rich) richToast.show(rich);
  else richToast.reset();
  $("notice-undo").hidden = !undo;
  noticeAction = action;
  $("notice-action").hidden = !action;
  if (action) $("notice-action").textContent = action.label;
  noticeAction2 = action2;
  $("notice-action2").hidden = !action2;
  if (action2) $("notice-action2").textContent = action2.label;
  notice.dataset.kind = kind;
  notice.hidden = false;
  clearTimeout(noticeTimer);
  if (sticky) return;
  noticeTimer = setTimeout(() => {
    notice.hidden = true;
  }, NOTICE_MS[kind]);
}
$("notice-action").addEventListener("click", () => noticeAction?.run());
$("notice-action2").addEventListener("click", () => noticeAction2?.run());
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

// The playhead between the engine's anchors (playhead-clock.js): drawn every animation
// frame while playing, so the cursor moves with the screen and with the sound.
const playheadClock = createPlayheadClock();
/** The playhead to draw now: extrapolated while playing, the state's when stopped. */
const playheadNow = (state = getState()) =>
  state.playing && playheadClock.playing()
    ? playheadClock.frameAt(performance.now())
    : state.playhead;

const transport = createTransport({
  post: api.transport,
  getState,
  setState,
  onError: showError,
  freeze: () => playheadClock.stop(performance.now()),
  settle: (status) => playheadClock.settle(status.position),
  jump: (frame) => playheadClock.jump(frame, performance.now()),
});

// While playing: every animation frame the timeline's cursor is drawn from the clock, and
// the state's playhead (clock, transcript, follow) follows at most ~30 times a second.
const PLAYHEAD_STATE_MS = 33;
let ticking = false;
let lastPlayheadPush = 0;
function tickPlayhead(now) {
  const state = getState();
  if (!state.playing || !playheadClock.playing()) {
    ticking = false;
    return;
  }
  timeline.redraw();
  const frame = playheadClock.frameAt(now);
  if (frame !== state.playhead && now - lastPlayheadPush >= PLAYHEAD_STATE_MS) {
    lastPlayheadPush = now;
    setState({ playhead: frame });
  }
  requestAnimationFrame(tickPlayhead);
}
function startPlayheadTicker() {
  if (ticking) return;
  ticking = true;
  requestAnimationFrame(tickPlayhead);
}

// The clipboard preview (WP46) has a clock of its own: its anchors ("preview" on the live
// channel) fill the playing chip's progress meter and never move the timeline's playhead.
// With animation off the meter steps four times a second instead of every frame.
let previewClock = createPlayheadClock();
let previewEnd = null;
let previewEndedSeq = null; // the newest "no preview plays" heard
let previewTicking = false;
let previewDrawn = 0;
const PREVIEW_STEP_MS = 250;
function startClipboardPreview(id, seq) {
  previewClock = createPlayheadClock();
  previewClock.setOffset(playheadClock.offset());
  previewEnd = null;
  let next = previewPlaying(getState().clipboardPlaying, { type: "start", id, seq });
  // A short excerpt can end before the answer that started it arrives.
  if (previewEndedSeq !== null && seq !== null) {
    next = previewPlaying(next, { type: "ended", seq: previewEndedSeq });
  }
  setState({ clipboardPlaying: next });
  if (next) startPreviewTicker();
}
function previewAnchor(message) {
  const current = getState().clipboardPlaying;
  if (!message.playing) {
    if (message.seq !== null && message.seq !== undefined) previewEndedSeq = message.seq;
    const next = previewPlaying(current, { type: "ended", seq: message.seq ?? null });
    if (next !== current) setState({ clipboardPlaying: next });
    return;
  }
  // An anchor from before this chip's preview started is the previous one's.
  if (!current || (current.seq !== null && (message.seq ?? 0) < current.seq)) return;
  if (previewClock.accept(message, performance.now())) previewEnd = message.end ?? null;
  startPreviewTicker();
}
function tickPreview(now) {
  if (!getState().clipboardPlaying) {
    previewTicking = false;
    return;
  }
  const stepped = document.documentElement.dataset.motion === "off";
  if (!stepped || now - previewDrawn >= PREVIEW_STEP_MS) {
    previewDrawn = now;
    const frame = previewClock.playing() ? previewClock.frameAt(now) : 0;
    clipboardPanel.progress(previewFraction(frame, previewEnd));
  }
  requestAnimationFrame(tickPreview);
}
function startPreviewTicker() {
  if (previewTicking) return;
  previewTicking = true;
  requestAnimationFrame(tickPreview);
}

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

// The side panel can be hidden so the timeline gets the width (sidebar-model.js): remembered per
// user, applied to the editor's data-sidebar in render(). Hiding it while the focus is inside
// sends the focus to the timeline; the commands that need it show it again (app-commands.js).
function setSidebar(shown) {
  if (shown === (getState().sidebarShown !== false)) return;
  if (!shown && document.querySelector(".sidebar")?.contains(document.activeElement)) {
    focusPanel("timeline");
  }
  setState({ sidebarShown: shown });
  prefs.set(SIDEBAR_KEY, sidebarPref(shown));
}
setState({ sidebarShown: sidebarShown(prefs.get(SIDEBAR_KEY)) });
// How lanes outside the current operation look (silence-visuals.js): dim, desaturate or both;
// remembered per user. <html data-inactive> lets the track headers follow (style.css).
const INACTIVE_KEY = "inactiveStyle";
function setInactiveStyle(style) {
  const choice = inactiveStyleChoice(style);
  setState({ inactiveStyle: choice });
  document.documentElement.dataset.inactive = choice;
  prefs.set(INACTIVE_KEY, choice);
}
setInactiveStyle(prefs.get(INACTIVE_KEY));

// -- focus mode (WP28, docs/design/FOCUS-MODE.md) ------------------------------------------------
// Shift+F: the current speaker's lanes take the room, the others become 16 px strips drawn
// inactive (focus-layout.js). `focusHeights` is a view layer over the lane heights (lanes.js
// layoutFor), never laneHeights, history or the project. The two switches are remembered per user.
const FOCUS_SHRINK_KEY = "focusShrink";
const FOCUS_HIDE_KEY = "focusHideOthers";
setState({
  focusMode: null,
  focusHeights: null,
  focusShrink: prefs.get(FOCUS_SHRINK_KEY) !== "off",
  focusHideOthers: prefs.get(FOCUS_HIDE_KEY) === "on",
});
let focusFrame = 0;
// A lane must not move under a drag (FOCUS-MODE.md "Drags in progress"): heights wait for release.
let pointerHeld = false;
let focusWaiting = null;
document.addEventListener(
  "pointerdown",
  () => {
    pointerHeld = true;
  },
  true,
);
for (const type of ["pointerup", "pointercancel"]) {
  document.addEventListener(
    type,
    () => {
      pointerHeld = false;
      // After the drag's own pointerup has dropped, so the drop sees the lanes it was over.
      if (focusWaiting) setTimeout(() => focusWaiting && resizeFocus(focusWaiting), 0);
    },
    true,
  );
}
const trackRowHeights = (state) =>
  Object.fromEntries(
    layoutFor(state)
      .rows.filter((row) => row.kind === "track")
      .map((row) => [row.id, row.height]),
  );
function focusTarget(state) {
  if (!state.focusMode || state.focusShrink === false) return null;
  return focusHeights({
    project: state.project,
    focusIds: state.focusMode.ids,
    available: laneArea(),
    busHeight: state.busHeight,
    groupGap: state.groupGap,
    collapsed: state.collapsedBuses,
  });
}
// Ease the lanes to their focus heights (or back): 120 ms, instant while playing or with
// Animation off or reduced motion (focusResizeMs). One rAF loop, so headers and canvas agree.
function resizeFocus({ animate = true } = {}) {
  if (pointerHeld) {
    focusWaiting = { animate };
    return;
  }
  focusWaiting = null;
  cancelAnimationFrame(focusFrame);
  const state = getState();
  const target = focusTarget(state);
  if (JSON.stringify(target) === JSON.stringify(state.focusHeights ?? null)) return;
  const mode = motionMode(motionChoice, reducedMotion.matches);
  const ms = animate ? focusResizeMs(mode, { playing: state.playing }) : 0;
  if (ms === 0) {
    setState({ focusHeights: target });
    return;
  }
  const from = trackRowHeights(state);
  const to = target ?? trackRowHeights({ ...state, focusHeights: null });
  const began = performance.now();
  const step = (now) => {
    const at = (now - began) / ms;
    setState({ focusHeights: at >= 1 ? target : tweenHeights(from, to, at) });
    if (at < 1) focusFrame = requestAnimationFrame(step);
  };
  focusFrame = requestAnimationFrame(step);
}
// Solo follows a focus entered with Alt+Shift+F; leaving puts the old solo set back. Additive
// solo toggles, which the server merges into one undo step.
function soloTo(target) {
  for (const id of soloSteps(getState().project?.tracks ?? [], target)) {
    editor.change({
      op: "solo",
      args: { track_id: id, exclusive: false },
      label: t("ui.edit.label.solo"),
    });
  }
}
function focusNames(state, ids) {
  const wanted = new Set(ids);
  return (state.project?.tracks ?? [])
    .filter((track) => wanted.has(track.id))
    .map((track) => track.name)
    .join(", ");
}
function setFocus(mode, current = null) {
  const state = getState();
  setState({
    focusMode: mode,
    ...(current ? { ...focusTrackPatch(state, current), rangeTracks: new Set() } : {}),
  });
  if (mode.soloBefore !== null) soloTo(mode.ids);
  resizeFocus();
}
function leaveFocus() {
  const { restoreSolo } = stopFocus(getState().focusMode);
  setState({ focusMode: null });
  if (restoreSolo !== null) soloTo(restoreSolo);
  resizeFocus();
  showNotice(t("ui.focus.off"), "ok");
}
function toggleFocus({ solo = false } = {}) {
  const state = getState();
  if (state.focusMode) {
    leaveFocus();
    return;
  }
  const mode = startFocus(state.project?.tracks ?? [], state.focusTrack, { solo });
  if (!mode) {
    showNotice(t("ui.focus.no_track"), "warn");
    return;
  }
  setFocus(mode);
  showNotice(t("ui.focus.on", { names: focusNames(state, mode.ids) }), "ok");
}
// Called from render: the focus follows a track made current elsewhere (a click on a strip),
// and the heights follow the project, the window and the switches. Deferred, so the other
// listeners of this change see the same state.
function focusChanged(state, touched) {
  if (!state.focusMode) {
    if (state.focusHeights && touched("project")) queueMicrotask(() => resizeFocus());
    return;
  }
  const tracks = state.project?.tracks ?? [];
  if (!tracks.some((track) => state.focusMode.ids.includes(track.id))) {
    queueMicrotask(leaveFocus);
    return;
  }
  if (touched("focusTrack")) {
    const ids = followCurrent(tracks, state.focusMode.ids, state.focusTrack);
    if (ids !== state.focusMode.ids) {
      queueMicrotask(() => setFocus({ ...getState().focusMode, ids }));
      return;
    }
  }
  if (touched("project", "collapsedBuses", "busHeight", "groupGap"))
    queueMicrotask(() => resizeFocus({ animate: false }));
  if (touched("focusShrink")) queueMicrotask(() => resizeFocus());
}

// The clipboard preview is turned down to the project's level (WP82): on by default, remembered
// per user. The server does the measuring; this is only the switch.
const CLIPBOARD_LIMIT_KEY = "clipboardLimit";
setState({ clipboardLimit: prefs.get(CLIPBOARD_LIMIT_KEY) !== "off" });
function toggleClipboardLimit() {
  const on = getState().clipboardLimit === false;
  setState({ clipboardLimit: on });
  prefs.set(CLIPBOARD_LIMIT_KEY, on ? "on" : "off");
  showNotice(t(on ? "ui.clipboard.limit.on" : "ui.clipboard.limit.off"), "ok");
}

// Quick mute length (seconds, Preferences); read by quickMutePlan from the state.
setState({ quickMuteS: normaliseQuickMute(prefs.get(QUICK_MUTE_KEY)) });
function setQuickMuteLength(seconds) {
  const value = normaliseQuickMute(seconds);
  setState({ quickMuteS: value });
  prefs.set(QUICK_MUTE_KEY, value);
}

// Set music level: how far under the speech the music's loudest moment goes (dB, Preferences).
setState({ musicUnderDb: normaliseMusicUnder(prefs.get(MUSIC_UNDER_KEY)) });
function setMusicUnder(db) {
  const value = normaliseMusicUnder(db);
  setState({ musicUnderDb: value });
  prefs.set(MUSIC_UNDER_KEY, value);
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

// Slow listening (WP26): Shift+J / Shift+L play slowed down while the key is held. Ignored while
// anything is playing (it never disturbs a run). Tape-style: the pitch follows the speed.
const SLOW_KEY = "slowSpeed";
setState({ slowSpeed: normaliseSlow(prefs.get(SLOW_KEY)) });
const slowHold = createSlowHold({
  canStart: () => Boolean(getState().project) && !getState().playing,
  start: (direction) => void transport.slowStart(slowSpeed(direction, getState().slowSpeed)),
  stop: () => void transport.slowStop(),
});
let slowTimer = null;
function slowListen(direction, event) {
  if (event?.type === "keydown") {
    slowHold.press(direction, event.code);
    return;
  }
  // From a menu or the palette there is no key to hold: listen for one second.
  clearTimeout(slowTimer);
  slowHold.press(direction, "menu");
  slowTimer = setTimeout(() => slowHold.cancel(), 1000);
}
function setSlowSpeed(speed) {
  setState({ slowSpeed: speed });
  prefs.set(SLOW_KEY, speed);
  const id = String(Math.round(speed * 100)).padStart(3, "0");
  showNotice(t("ui.slow.now", { speed: t(`cmd.transport.slow_speed_${id}`) }), "ok");
}

const actions = {
  slowListen,
  slowRelease: (code) => slowHold.release(code),
  slowCancel: () => slowHold.cancel(),
  setSlowSpeed,
  slowInfo: () => showNotice(t("ui.slow.info"), "ok"),
  togglePlay: () => void transport.toggle(),
  playFrom: (frame) => void transport.play(frame),
  playRequest: (request) => {
    if (request) void transport.preview(request.at, request.until, request.skip);
  },
  shuttle: (key) => void transport.press(key),
  toggleLoop: () => setState({ loop: !getState().loop }),
  toggleRenderListen: () => void setRenderListen(getState().render?.listening !== true),
  toggleDragMode: () => toggleDragMode(),
  toggleWheelMode: () => toggleWheelMode(),
  toggleClipWords: () => toggleClipWords(),
  toggleFocus: (options) => toggleFocus(options),
  setFocus: (mode, current) => setFocus(mode, current),
  toggleFocusShrink() {
    const on = getState().focusShrink === false;
    setState({ focusShrink: on });
    prefs.set(FOCUS_SHRINK_KEY, on ? "on" : "off");
    showNotice(t(on ? "ui.focus.shrink_on" : "ui.focus.shrink_off"), "ok");
  },
  toggleFocusHideOthers() {
    const on = getState().focusHideOthers !== true;
    setState({ focusHideOthers: on });
    prefs.set(FOCUS_HIDE_KEY, on ? "on" : "off");
    showNotice(t(on ? "ui.focus.hide_on" : "ui.focus.hide_off"), "ok");
  },
  toggleSidebar() {
    const shown = toggleSidebar(getState().sidebarShown !== false);
    setSidebar(shown);
    showNotice(t(shown ? "ui.sidebar.on" : "ui.sidebar.off"), "ok");
  },
  setInactiveStyle: (style) => setInactiveStyle(style),
  toggleClipboardLimit: () => toggleClipboardLimit(),
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
      trackSelection: state.trackSelection,
      rangeMode: state.rangeMode,
      focusMode: state.focusMode,
    });
    if (what === "blur") active.blur();
    if (what === "leave_focus") leaveFocus();
    if (what === "clear_tracks") setState(clearTrackSelection());
    // Clear the clip selection, the range and the in and out marks (owner, 2026-10-18).
    if (what === "clear") {
      setState({ selection: new Set(), rangeTracks: new Set(), inPoint: null, outPoint: null });
    } else focusPanel("timeline");
  },
  showSideTab: (name) => focusPanel(name),
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
  /** View > Language: stored on the server (its messages follow), applied here at once. */
  async setLanguageChoice(choice) {
    try {
      await api.putLanguage(choice);
    } catch (error) {
      showNotice(t("ui.language.failed", { error: error.message }));
      return;
    }
    setState({ languageChoice: choice });
    try {
      await setLanguage(choice === "auto" ? detectLanguage() : choice);
    } catch (error) {
      showError(error);
    }
  },
  /** Help > Log level: kept on the server (applies at once, and next start). */
  async setLogLevel(level) {
    try {
      const answer = await api.putLogLevel(level);
      setState({ logLevel: answer.level });
      showNotice(t("ui.loglevel.now", { level: answer.level }), "ok");
    } catch (error) {
      showError(error);
    }
  },
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
// "Keep the mic open under the selected clips": a clip property (Clip.ungated), one edit. It
// toggles: when every selected clip is already open it lets them be gated again.
function openGateUnderClips() {
  const state = getState();
  if (state.selection.size === 0) return;
  editor.change(underClipsEdit(state.project, [...state.selection], t));
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
  // Cmd/Ctrl on a clip edge starts "trim only this clip", not an additive pick: the press
  // leaves the selection and the play cursor as they are (the least surprising: nothing
  // changes until the drag does). Cmd+Alt on an edge keeps its "select from here" meaning.
  if (
    hit.clip &&
    hit.edge &&
    hit.row?.kind === "track" &&
    edgePressKeepsSelection({ mod, alt: event.altKey })
  ) {
    setState({ panel: "timeline" });
    return;
  }
  const patch = { panel: "timeline", rangeTracks: new Set() };
  if (hit.row?.kind === "track" && !additive) {
    // A lane or clip click makes the track current but leaves the range scope on all tracks
    // (range-scope.js laneClickFocus); only a header click narrows it.
    Object.assign(patch, laneClickFocus(state, hit.row.id));
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
  if (SIDEBAR_TABS.includes(name)) {
    setSidebar(true);
    setState({ sidebarTab: name });
  }
  panelElements[name].focus();
  setState({ panel: name });
}

document.addEventListener("focusin", (event) => {
  const panel = event.target.closest?.("[data-panel]")?.dataset.panel;
  if (panel && panel !== getState().panel) setState({ panel });
});

$("side-close").addEventListener("click", () => actions.toggleSidebar());
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
// Esc and Enter in modal dialogs (dialog-keys.js): before the keymap sees the key.
installDialogKeys(window);

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
    tabKeyEntries = entries;
    applyTabs();
  },
  app: {
    getState,
    patch: setState,
    openHelp: () => void help.open(),
    revealSidebar: () => setSidebar(true),
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
    seriesShelf: (id, on) => seriesShelfEntry(id, on),
    showClipboard: (view) => showClipboard(view),
    openClipboardProject: () => void openClipboardProject(),
    rememberRange: () => {
      const { head, inPoint, outPoint, rangeTracks } = getState();
      rangeMemory = rememberRange(head, { inPoint, outPoint, rangeTracks });
    },
    previewClipboard: (id) =>
      api
        .previewClipboardEntry(id, getState().clipboardLimit !== false)
        .then((answer) => {
          // How far the preview was turned down, for the hint beside the entry.
          setState({ clipboardLevel: { id, db: answer?.attenuation_db ?? 0 } });
          if (answer?.started) startClipboardPreview(id, answer.seq ?? null);
          return answer;
        })
        .catch((error) => {
          showError(error);
          return null;
        }),
    now: () => performance.now(),
    chooseMedia: () => chooseMedia(),
    // The transcript's X: cut the words' stretch on every track.
    cutWords: (indices) => {
      const scope = resolveScope(getState());
      if (scope.none) {
        showNotice(t("ui.scope.none_selected"), "warn");
        return Promise.resolve(false);
      }
      return api
        .command("cut_words", { indices, track_ids: scope.tracks })
        .then((response) => {
          apply(response);
          return true;
        })
        .catch((error) => {
          showError(error);
          return false;
        });
    },
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
    automixLog: () => void openAutomixLog(),
    openStatistics: () => void openStatistics(),
    openPerformanceReport: () => void openPerformanceReport(),
    openLocateMedia: () => void openLocateMedia(),
    relinkClipMedia: () => void relinkClipMedia(),
    openSendCopy: () => void openSendCopy(),
    openSeries: () => void openSeries(),
    seriesSave: () => void seriesSave(),
    seriesApply: () => void seriesApply(),
    newEpisode: () => void openNewEpisode(),
    seriesMusicAdd: () => void seriesMusicAdd(),
    seriesMusicPlace: () => void seriesMusicPlace(),
    seriesMusicClipboard: () => void seriesMusicClipboard(),
    openRecord: () => void recordView.open(),
    cycleStopMode: () => cycleStopMode(),
    cyclePreroll: () => cyclePreroll(),
    autoSilence: () => void autoSilence(),
    openSilenceOptions: () => openSilenceOptions(),
    // Calculate Auto-Silence values from the selection: the panel, learning first.
    learnSilence: () => openSilenceOptions({ clipIds: [...getState().selection] }),
    openMusicLevel: () => openMusicLevel(),
    openBlockLevel: () => openBlockLevel(),
    duckMusic: () => void duckMusic(),
    openAllGates: () => void openAllGates(),
    openGateUnderClips: () => openGateUnderClips(),
    duckMicrophones: () => void duckMicrophones(),
    transcribeTrack: (backend) => void transcribeTrack(backend),
    restartTranscriptions: () => void restartTranscriptions(),
    openColabSettings: () => void colabDialogsFor().openSettings(),
    openColabSignin: () => void colabDialogsFor().signIn(),
    exportTracks: (format, options) => exportTracks(format, options),
    exportMix: (format, options) => exportMix(format, options),
    exportQuick: (force) => exportQuick(force),
    exportFormats: () => exportFormatIds,
    openExportDialog: (what) => openExportDialog(what),
    newProject: () => void newProject(),
    openProject: () => void openProject(),
    closeProject: () => void closeProject(),
    openPreferences: () => openPreferences(),
    minimise: () => void minimise(),
    openRecent: (path) => void openRecent(path),
    clearRecent: () => void clearRecent(),
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
$("scope-chip").addEventListener("click", () => setState(toggleScopeMode(getState())));
$("series-chip").addEventListener("click", () => void openSeries());
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
    // A track header becomes current (range-scope.js focusTrack: the one rule that keeps the
    // header selection in step). mode: "select" (click), "add" (Cmd+click), "follow" (focus).
    currentTrack: (id, options) => {
      // A header is the timeline's keyboard context (Tab, arrows); the panel was left as it was.
      setState({ ...focusTrackPatch(getState(), id, options), ...headerFocusPatch(getState()) });
    },
    // The kind tag in a track header: focus the track, then the same command as Alt+Mod+K.
    cycleKind: (id) => {
      setState(focusTrackPatch(getState(), id));
      keyboard.registry.run("track.cycle_kind", null, getState());
    },
    // The role badge on a track header, and the "Reapply" button on a bus header.
    matchRole: (id) => {
      setState(focusTrackPatch(getState(), id));
      keyboard.registry.run("track.match_role", null, getState());
    },
    reapplyRole: (id) => {
      setState({ focusBus: id, focusTrack: null });
      keyboard.registry.run("bus.reapply_role", null, getState());
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
  if (kind === "track") setState({ ...focusTrackPatch(getState(), id), selection: new Set() });
  else setState({ focusBus: id, focusTrack: null });
  const state = getState();
  const track = state.project.tracks.find((item) => item.id === id);
  const target =
    kind === "bus"
      ? {
          kind,
          collapsed: state.collapsedBuses.has(id),
          role: state.project.buses.find((bus) => bus.id === id)?.kind ?? null,
        }
      : {
          kind,
          choice: trackRoleChoice(state.project, track),
          busRole: state.project.buses.find((bus) => bus.id === track?.bus)?.kind ?? null,
        };
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
    Object.assign(patch, focusTrackPatch(getState(), hit.row.id));
  }
  if (plan.focusTrack) Object.assign(patch, focusTrackPatch(getState(), plan.focusTrack));
  setState(patch);
  if (plan.seek !== null) void transport.seek(plan.seek);
  const sections = timelineMenuItems(
    getState(),
    { kind: plan.kind, gate: Boolean(plan.gate) },
    (id, state) => keyboard.registry.can(id, state),
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
    onPick: (command) => {
      // The stretch under the pointer is opened directly (the command's usual target is
      // the one under the play cursor).
      if (command === "gate.open_stretch" && plan.gate) openGateStretch(plan.gate);
      else keyboard.registry.run(command, null, getState());
    },
  });
}
const inspector = createInspector({
  root: $("panel-inspector"),
  editor,
  fetchMap: api.getSourceMap,
  onBusCreated: nameNewBus,
  // A row of the Source list: select that clip and move the play cursor to it.
  jump: (clip, track, frame) => {
    setState({
      ...focusTrackPatch(getState(), track),
      selection: new Set([clip]),
      panel: "timeline",
    });
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
    let rich = null;
    if (what === "automix") {
      const view = automixToast(job, t);
      notice = view.notice;
      if (view.rich) rich = view;
    } else if (what === "colab") notice = colabNotice(job, t, colabNames);
    else notice = exportNotice(job, t, what);
    let action = null;
    if (notice.cancel) {
      action = { label: t("ui.export.cancel"), run: () => void cancelExportJob() };
    } else if (notice.reveal && typeof bridge?.reveal_export === "function") {
      action = { label: t("ui.export.show_in_finder"), run: () => void bridge.reveal_export() };
    }
    let action2 = null;
    // While the automixer runs, Show log opens the live viewer (Cancel keeps its place).
    if (what === "automix" && notice.cancel) {
      action2 = { label: t("ui.automix.show_log"), run: () => void openAutomixLog() };
    }
    if (notice.log && typeof bridge?.reveal_automix_log === "function") {
      action2 = {
        label: t("ui.automix.show_log"),
        run: () => void bridge.reveal_automix_log(),
      };
      action ??= action2;
      if (action === action2) action2 = null;
    }
    // Done stays up (the owner reads the folder); failures and cancels time out as usual.
    showNotice(notice.text, notice.kind, { sticky: notice.sticky, action, action2, rich });
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
async function startExport(what, format, { ask = true, extra = {} } = {}) {
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
    const body = { ...extra, ...options };
    const { jobs } = await (what === "mix" ? api.exportMix(body) : api.exportTracks(body));
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
    pickFolder: folderChooser(),
    prefs,
    onSetMusicLevel: () => openMusicLevel(),
    onLevelBlocks: () => openBlockLevel(),
    onDuckMusic: () => void duckMusic(),
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
  const state = getState();
  // "Only the In/Out range (a quick preview)": offered while both marks make a range.
  await automixDialog.open({
    range: rangeChoice({
      inPoint: state.inPoint,
      outPoint: state.outPoint,
      length: totalFrames(),
      rate: rate(),
    }),
    rate: rate(),
  });
}

// Edit | Rendered mix: the server swaps what the engine plays; the answer is the state.
async function setRenderListen(on) {
  try {
    apply(await api.renderListen(on));
  } catch (error) {
    showError(error);
    void refresh(); // a refusal (stale, missing) also redraws the switch as it now is
  }
}

// "Show automixer log…": everything the automixer printed so far, live while it runs.
let automixLiveDialog = null;
async function openAutomixLog() {
  automixLiveDialog ??= createAutomixLiveDialog({
    api,
    t,
    copyText: async (text) => {
      try {
        await navigator.clipboard.writeText(text);
        showNotice(t("ui.automix.live_copied"), "ok");
      } catch (error) {
        showError(error);
      }
    },
  });
  await automixLiveDialog.open();
}

// File > Statistics… (WP70): the server counts and words it; the dialog shows, copies, saves.
let statsDialog = null;
/** The Auto-Silence options remembered for this project (view memory), else the defaults. */
const silenceOptions = () => normaliseSilence(getState().autoSilence);

/**
 * Track > Auto > Auto-Silence (Alt+Mod+P): close each speech mic where its owner is not
 * talking, with the options remembered for this project; one undo step. `options` is the
 * dialog's choice.
 */
async function autoSilence(options = silenceOptions()) {
  try {
    apply(await api.command("auto_silence", options));
    showNotice(t("ui.auto_silence.done"), "ok", { undo: true });
  } catch (error) {
    showError(error);
  }
}

let duckMusicJob = null;
const DUCK_MUSIC_PREF = "duckMusicStyle";

/** Track > Auto > Duck music: analyze in a cancellable job, then make one history edit. */
async function runDuckMusic(options = { style: "gaps" }) {
  if (duckMusicJob) return;
  try {
    const { jobs } = await api.duckMusicMeasure(options);
    const id = jobs[0];
    duckMusicJob = id;
    const cancel = async () => {
      if (duckMusicJob !== id) return;
      duckMusicJob = null;
      try {
        await api.cancelJob(id);
      } catch (error) {
        showError(error);
      }
    };
    showNotice(t("ui.duck_music.measuring"), "ok", {
      sticky: true,
      action: { label: t("ui.export.cancel"), run: () => void cancel() },
    });
    while (duckMusicJob === id) {
      const job = (await api.getJobs()).jobs.find((item) => item.id === id);
      if (!job) break;
      if (job.state === "completed") {
        duckMusicJob = null;
        apply(await api.command("duck_music", { measured: job.result, style: options.style }));
        showNotice(t("ui.duck_music.done"), "ok", { undo: true });
        return;
      }
      if (job.state === "failed" || job.state === "cancelled") {
        duckMusicJob = null;
        if (job.state === "failed") showError(job.error?.text || t("ui.duck_music.failed"));
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
  } catch (error) {
    showError(error);
  } finally {
    duckMusicJob = null;
  }
}

let duckMusicDialog = null;
function duckMusic() {
  duckMusicDialog ??= createDuckMusicDialog({
    t,
    fmt: (value) => String(Math.round(Math.abs(value) * 10) / 10),
    getSettings: () => normaliseDuckMusic(prefs.getJson(DUCK_MUSIC_PREF, DUCK_MUSIC_DEFAULTS)),
    onRemember: (value) => prefs.setJson(DUCK_MUSIC_PREF, value),
    onApply: (options) => void runDuckMusic(options),
  });
  duckMusicDialog.open();
}

/**
 * Track > Auto > Auto-Silence options…: the live preview panel, docked over the sidebar. The
 * timeline shows and the engine plays what the options would close; Accept commits it as one
 * undo step, Close discards it.
 */
function openSilenceOptions(learnFrom = null) {
  silencePanel ??= createSilencePanel({
    root: $("panel-silence"),
    api,
    t,
    getProject: () => getState().project,
    getOptions: silenceOptions,
    onRemember: (options) => setState({ autoSilence: options }),
    onAccepted: (response) => {
      apply(response);
      showNotice(t("ui.auto_silence.done"), "ok", { undo: true });
    },
    setPreview: (ranges) => setState({ silencePreview: ranges }),
    isPlaying: () => Boolean(getState().playing),
    togglePlay: () => actions.togglePlay(),
    hideSidebar: () => actions.toggleSidebar(),
  });
  silencePanel.open(learnFrom);
}

/**
 * Track > Auto > Set music level…: the dialog measures (a job), Apply sets the music tracks'
 * gain as one undo step and the notice says where the music now sits against the speech.
 */
let musicLevelDialog = null;
function openMusicLevel() {
  musicLevelDialog ??= createMusicLevelDialog({
    api,
    t,
    fmt: (value) => formatNumber(value, { digits: 1 }),
    getOffset: () => getState().musicUnderDb,
    onRemember: setMusicUnder,
    onApply: (args) => void setMusicLevel(args),
  });
  musicLevelDialog.open();
}

async function setMusicLevel(args) {
  try {
    const response = await api.command("set_music_level", args);
    apply(response);
    const report = response.music_level;
    const text = report?.clamped?.length
      ? `${report.text} ${t("ui.music_level.clamped")}`
      : report?.text;
    showNotice(text ?? t("history.set_music_level"), "ok", { undo: true });
  } catch (error) {
    showError(error);
  }
}

/**
 * Track > Auto > Level blocks…: the dialog measures (a job) and lists the blocks that are off;
 * Apply splits the clips in the pauses and adds the gains, as one undo step.
 */
let blockLevelDialog = null;
function openBlockLevel() {
  blockLevelDialog ??= createBlockLevelDialog({
    api,
    t,
    fmt: (value) => formatNumber(value, { digits: 1 }),
    clock: (seconds) => formatClock(seconds),
    onApply: (args) => void levelBlocks(args),
  });
  blockLevelDialog.open();
}

async function levelBlocks(args) {
  try {
    const response = await api.command("level_blocks", args);
    apply(response);
    const report = response.block_level;
    const more = [];
    if (report?.clamped) more.push(t("ui.block_level.clamped"));
    if (report?.left_out) more.push(t("ui.block_level.left_out"));
    const text = [report?.text, ...more].filter(Boolean).join(" ");
    showNotice(text || t("ui.block_level.title"), "ok", { undo: true });
  } catch (error) {
    showError(error);
  }
}

/** Track > Auto > Open all gates on this track: one undo step. */
async function openAllGates() {
  const track = getState().focusTrack;
  if (!track) {
    showNotice(t("ui.gate.no_track"), "error");
    return;
  }
  try {
    apply(await api.command("open_gates", { track_ids: [track] }));
    showNotice(t("ui.gate.all_open"), "ok", { undo: true });
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
 * Text > Transcribe > On this computer / On Colab: the focused track's recordings, else every
 * speech track's. Colab uploads the audio to Google, so it asks first (transcribeOnColab).
 */
async function transcribeTrack(backend = "local") {
  const state = getState();
  const track = state.project?.tracks.find((item) => item.id === state.focusTrack);
  const asked = track ? [...new Set(track.clips.map((clip) => clip.media))] : undefined;
  // Music is not transcribed (nor uploaded): a music-only track gives a notice, not a job.
  const ids = asked && withoutMusic(state.project, asked);
  if (asked && ids.length === 0) {
    showNotice(t("ui.transcript.music_skipped"), "error");
    return;
  }
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

// Text > Transcribe > Restart interrupted transcriptions.
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
    onSignedIn: () => showNotice(t("ui.colab.signin_ok"), "ok"),
  });
  return colabDialogs;
};

/** Is Colab signed in to Google? When not, the sign-in dialog opens; resolves whether it is now. */
async function ensureColabSignedIn() {
  try {
    if ((await api.colabSignin()).signed_in) return true;
  } catch (error) {
    showError(error);
    return false;
  }
  return colabDialogsFor().signIn();
}

async function transcribeOnColab(ids) {
  const project = getState().project;
  if (exportJob || !project || !ids || ids.length === 0) return;
  const names = project.media
    .filter((item) => ids.includes(item.id))
    .map((item) => item.name)
    .join(", ");
  // The Google sign-in is interactive, so it happens here, before any job exists (a detached
  // worker has no terminal to ask in). Nothing is uploaded and no job is made until it is done.
  if (!(await ensureColabSignedIn())) return;
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
    void transcript.refreshJobs();
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

let perfDialog = null;

// Help > Record a performance report… : the app samples its own threads for a while and writes
// a text file next to the log (src/kuulas/profiler.py). Works without a project.
async function openPerformanceReport() {
  perfDialog ??= createPerfDialog({
    api,
    t,
    notify: (text, kind) => showNotice(text, kind),
  });
  await perfDialog.open();
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
// Clip > Locate / Relink media… (relink-media.js): pick a file for the selected clip's
// recording; the server imports it in place and reports; confirm; one replace_clip_media edit.
let relinkConfirm = null;
async function relinkClipMedia() {
  const state = getState();
  const [clipId] = [...state.selection];
  const clip = state.project?.tracks.flatMap((track) => track.clips).find((c) => c.id === clipId);
  if (!clip) return;
  try {
    const bridge = nativeBridge();
    const path = bridge
      ? (await bridge.pick_media())?.[0]
      : globalThis.prompt?.(t("ui.relink.path_prompt"));
    if (!path) return;
    const report = await api.replaceCheck(clip.media, path);
    const rate = state.project.rate;
    const seconds = (frames) => `${formatNumber(frames / rate, { digits: 1 })} s`;
    const plan = relinkPlan(report, { t, seconds, mediaId: clip.media });
    if (!plan.confirm) {
      await refresh();
      showNotice(plan.notice, "ok");
      return;
    }
    relinkConfirm ??= createRelinkConfirm({ t });
    if (!(await relinkConfirm.ask(plan))) return;
    apply(await api.edit({ ...plan.edit, label: t("ui.relink.history") }));
    showNotice(t("ui.relink.done"), "ok", { undo: true });
  } catch (error) {
    showError(error);
  }
}

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
// File > Series (docs/design/SERIES.md): settings shared by the episodes of a show. The server
// holds the series and says what differs; the status-bar chip shows it. Nothing is applied
// unless one of these commands is run.
const pageSilence = () => {
  const options = getState().autoSilence;
  return options ? normaliseSilence(options) : null;
};
let seriesDialog = null;
let episodeDialog = null;
async function refreshSeries() {
  if (!getState().project?.series?.id) {
    if (getState().series) setState({ series: null });
    return;
  }
  try {
    setState({ series: await api.seriesStatus(pageSilence()) });
  } catch {
    // The chip is a help: a failed look keeps the last verdict; the next change looks again.
  }
}
let seriesTimer = null;
let seriesHead = null;
function scheduleSeriesRefresh(state) {
  if (state.head === seriesHead) return;
  seriesHead = state.head;
  clearTimeout(seriesTimer);
  seriesTimer = setTimeout(() => void refreshSeries(), 1500);
}
/** An answer that changed the project (save, apply, attach, detach, rename, place). */
function seriesChanged(response) {
  apply(response);
  if (response.settings?.auto_silence) {
    setState({ autoSilence: normaliseSilence(response.settings.auto_silence) });
  }
  if (response.series) setState({ series: response.series });
  void loadSeriesShelf();
}
function updateSeriesChip(state) {
  const chip = seriesChip(state, t);
  const el = $("series-chip");
  el.hidden = chip === null;
  if (chip === null) return;
  el.textContent = chip.text;
  el.title = chip.title;
  el.classList.toggle("warn", chip.differs);
}
async function openSeries() {
  seriesDialog ??= createSeriesDialog({
    api,
    t,
    getAutoSilence: pageSilence,
    onChanged: seriesChanged,
    notify: (text) => showNotice(text, "ok"),
  });
  await seriesDialog.open();
}
// Saving changes what every later episode starts from and has no undo (the series file is not
// project state), so it always goes through the dialog: the save button has the focus there.
const seriesSave = () => openSeries();
async function seriesApply() {
  try {
    seriesChanged(await api.seriesApply());
    showNotice(t("ui.series.applied", { name: getState().project?.series?.name ?? "" }), "ok", {
      undo: true,
    });
  } catch (error) {
    showError(error);
  }
}
async function openNewEpisode() {
  const bridge = globalThis.pywebview?.api;
  episodeDialog ??= createNewEpisodeDialog({
    api,
    t,
    openFolder:
      typeof bridge?.open_path_in_window === "function"
        ? (path) => bridge.open_path_in_window(path)
        : null,
    notify: (text) => showNotice(text, "ok"),
  });
  await episodeDialog.open();
}
async function seriesMusicAdd() {
  const clips = [...(getState().selection ?? [])];
  try {
    const answer = await api.seriesMusicAdd(clips);
    setState({ series: answer });
    void loadSeriesShelf();
    showNotice(t("ui.series.music_added", { count: answer.music }), "ok");
  } catch (error) {
    showError(error);
  }
}
async function seriesMusicPlace() {
  try {
    const response = await api.seriesMusicPlace();
    apply(response);
    const { placed, missing, skipped } = response.placed;
    const parts = [t("ui.series.music_placed", { count: placed })];
    if (missing.length) parts.push(t("ui.series.music_missing", { count: missing.length }));
    if (skipped.length) parts.push(t("ui.series.music_skipped", { names: skipped.join(", ") }));
    showNotice(parts.join(" "), "ok", { undo: placed > 0 });
  } catch (error) {
    showError(error);
  }
}
async function seriesMusicClipboard() {
  try {
    const { added } = await api.seriesMusicClipboard();
    await refreshClipboard();
    showNotice(t("ui.series.music_clipboard_done", { count: added }), "ok");
  } catch (error) {
    showError(error);
  }
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

// What each project last exported (scope, chosen tracks, whether to ask for the folder),
// remembered per user and project (the project's path); the format, quality and loudness the
// server remembers in the project (GET /api/export-settings).
const scopeKey = (project) => `exportscope.${project}`;
const scopeMemory = (project) => prefs.getJson(scopeKey(project), null);
let exportProject = "";

/**
 * Mod+E (and Export in/out range, `force` "range"): export at once with the project's last
 * scope and settings. When the remembered scope cannot be had (no marks now, the tracks are
 * gone) the options open and say why, instead of exporting something else.
 */
async function exportQuick(force) {
  if (exportJob) return;
  try {
    const server = await api.exportSettings();
    exportProject = server.project;
    const state = getState();
    const plan = quickPlan({
      memory: scopeMemory(server.project),
      marks: state,
      project: state.project,
      force,
    });
    if (plan.dialog) {
      showNotice(t(plan.dialog), "ok");
      void openExportDialog("mix");
      return;
    }
    await startExport(plan.what, undefined, { ask: false, extra: plan.body });
  } catch (error) {
    showError(error);
  }
}

// File > Export mix (options)… / Export all tracks (options)… (WP74): format, and whether to
// choose the folder first (only the desktop window has a folder chooser).
let exportDialog = null;
function openExportDialog(what) {
  exportDialog ??= createExportDialog({
    t,
    formats: () => exportFormatList,
    canChooseFolder: () => typeof globalThis.pywebview?.api?.choose_export_folder === "function",
    context: async () => {
      const server = await api.exportSettings();
      exportProject = server.project;
      return {
        server,
        memory: scopeMemory(server.project),
        state: getState(),
        frames: totalFrames(),
      };
    },
    saveMemory: (memory) => prefs.setJson(scopeKey(exportProject), memory),
    onStart: ({ what: kind, body, ask }) => startExport(kind, body.format, { ask, extra: body }),
  });
  void exportDialog.open(what).catch(showError);
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

// -- the standard Mac commands (owner, 2026-10-19) -------------------------------------------
// Close project, Open Recent and Minimise talk to the desktop window (src/kuulas/desktop.py);
// in a plain browser tab there is no window to close and no recents list, so they say so.

/** File > Close project (Cmd+W): back to the start page. The window refuses while a take records. */
async function closeProject() {
  const bridge = globalThis.pywebview?.api;
  if (typeof bridge?.close_project !== "function") {
    showNotice(t("ui.project.close_desktop_only"));
    return;
  }
  // A running take is the recorder's, not this page's, but it is never walked away from.
  if (recordView.isRecording()) {
    showNotice(t("ui.project.close_recording"), "error");
    return;
  }
  try {
    const answer = await bridge.close_project();
    if (answer?.closed === false) {
      showNotice(
        t(answer.reason === "recording" ? "ui.project.close_recording" : "ui.project.close_armed"),
        "error",
      );
    }
  } catch (error) {
    showNotice(t("ui.project.close_failed", { error: error?.message ?? String(error) }), "error");
  }
}

/** View > Minimise (Cmd+M): the window goes to the Dock. */
async function minimise() {
  const bridge = globalThis.pywebview?.api;
  if (typeof bridge?.minimise !== "function") {
    showNotice(t("ui.window.minimise_desktop_only"));
    return;
  }
  try {
    await bridge.minimise();
  } catch (error) {
    showError(error);
  }
}

// File > Open Recent: the start page's records, read from the desktop window (the same
// recent.json); state.recentProjects holds the menu's entries (recent-menu-model.js).
async function refreshRecent() {
  const bridge = globalThis.pywebview?.api;
  if (typeof bridge?.recent_records !== "function") return;
  try {
    const records = await bridge.recent_records();
    setState({
      recentProjects: recentMenuItems(records, { nowMs: Date.now(), lang: getLanguage() }),
    });
  } catch {
    // The list is a convenience; the menu keeps what it had.
  }
}
window.addEventListener("pywebviewready", () => void refreshRecent());
window.addEventListener("focus", () => void refreshRecent());
onLanguageChange(() => void refreshRecent());
void refreshRecent();

async function openRecent(path) {
  const bridge = globalThis.pywebview?.api;
  if (typeof bridge?.open_recent_in_window !== "function") return;
  try {
    if ((await bridge.open_recent_in_window(path)) === false) {
      showNotice(t("ui.project.recent_missing", { path }), "error");
    }
  } catch (error) {
    showError(error);
  }
  void refreshRecent();
}

async function clearRecent() {
  const bridge = globalThis.pywebview?.api;
  if (typeof bridge?.clear_recent !== "function") return;
  try {
    await bridge.clear_recent();
    showNotice(t("ui.project.recent_cleared"), "ok", { undo: false });
  } catch (error) {
    showError(error);
  }
  void refreshRecent();
}

// File > Preferences… (Cmd+,): every control calls the setter of the setting's own menu command.
let preferencesDialog = null;
function openPreferences() {
  preferencesDialog ??= createPreferencesDialog({
    t,
    read: () => ({
      state: getState(),
      record: { stopMode: recordView.stopMode, preroll: recordView.preroll },
    }),
    setters: {
      language: (choice) => void actions.setLanguageChoice(choice),
      stopMode: (mode) => recordView.setStopMode(mode),
      preroll: (seconds) => recordView.setPreroll(seconds),
      confirmSync: (on) => {
        if (on !== (getState().confirmSync !== false)) toggleConfirmSync();
      },
      clipboardLimit: (on) => {
        if (on !== (getState().clipboardLimit !== false)) toggleClipboardLimit();
      },
      fast: (speed) => changeFast((fast) => setFast(fast, speed)),
      quickMute: (seconds) => setQuickMuteLength(seconds),
      musicUnder: (db) => setMusicUnder(db),
    },
    run: (command) => keyboard.registry.run(command, null, getState()),
    canRun: (command) => keyboard.registry.can(command, getState()),
  });
  preferencesDialog.open();
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
  void loadSeriesShelf();
}

// -- the series shelf (docs/design/CLIPBOARD-SHELVES.md) ------------------------------------------

const seriesShelf = createSeriesShelf({
  api,
  t,
  setState,
  notify: (text) => showNotice(text, "ok", { undo: false }),
  showError: (error) => showError(error),
});
const loadSeriesShelf = () => seriesShelf.load();
// The Series toggle of a project entry: a copy on the series shelf (same id), or off it again.
const seriesShelfEntry = (id, on) => seriesShelf.toggle(id, on);

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
  if (view === "series") void loadSeriesShelf();
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
// the newest entry and is picked, so the paste keys paste it. Returns the copy, or null.
async function adoptClipboardEntry(entry, from, { quiet = false, shelf = "" } = {}) {
  try {
    const answer = await adoptRequest(api, entry, from, shelf);
    setState({ clipboard: answer.entries, clipboardSelected: answer.entry.id });
    if (!quiet) {
      showNotice(t("ui.clipboard.adopted", { name: entryTitle(answer.entry, rateOf(), t) }), "ok", {
        undo: false,
      });
    }
    return answer.entry;
  } catch (error) {
    showError(error);
    return null;
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
const pasteCommand = (state) => (state.pasteMode === "insert" ? "edit.paste_insert" : "edit.paste");

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
    adopt: (entry, from, shelf = "") => void adoptClipboardEntry(entry, from, { shelf }),
    async pasteHere(entry, from, shelf = "") {
      if (await adoptClipboardEntry(entry, from, { quiet: true, shelf })) {
        keyboard.registry.run(pasteCommand(getState()), null, getState());
      }
    },
    keep: (value) => setState({ clipboardKeep: Number(value) }),
    clearOld: () => keyboard.registry.run("edit.clear_old_clipboard", null, getState()),
    preview(id) {
      setState({ clipboardSelected: id });
      keyboard.registry.run("edit.preview_clipboard", null, getState());
    },
    // The playing chip's Stop. Mixed into a playing timeline only its voice goes away and the
    // timeline plays on; played alone, the transport's stop ends it (the playhead goes back).
    stopPreview() {
      if (previewStop(getState()) === "preview") {
        setState({ clipboardPlaying: null });
        void api.stopClipboardPreview().catch(showError);
      } else {
        void transport.stop();
      }
    },
    canPasteAgain: (state) => keyboard.registry.can(pasteCommand(state), state),
    seriesShelf: (id, on) => void seriesShelfEntry(id, on),
    seriesRemove: (id) => void seriesShelfEntry(id, false),
    seriesPlace: () => keyboard.registry.run("series.music_place", null, getState()),
    openSeries: () => keyboard.registry.run("series.dialog", null, getState()),
    dragStart: (entry, source) => clipboardDrag.start(entry, source),
    dragEnd: () => clipboardDrag.end(),
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
      focusMode: Boolean(state.focusMode),
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
  playheadAt: playheadNow,
  actions: {
    pointerDown: onPointerDown,
    seek: (frame) => void transport.seek(frame),
    contextMenu: (hit, event) => showTimelineMenu(hit, event),
    rangeDragged: onRangeDragged,
    clipDrag({ ids, move, alone = false }) {
      // Alt held: it then asks whether the clip should stay free from sync (owner, 2026-10-16).
      // Nothing but an explicit group moves along with it (WP83).
      const change = clipDragChange(ids, move);
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
    // Double-click on the gain line: the envelope's new points, one undo step.
    clipEnvelope({ clipId, points }) {
      const { op, args, labelKey } = envelopeChange(clipId, points);
      editor.change({
        op,
        args,
        label: t(labelKey),
        provisional: (p) => patchClip(p, clipId, { envelope: points }),
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
    edgeDrag({ clipId, edge, frame, ripple, overwrite, alone }) {
      const { op, args, labelKey } = edgeChange(
        clipId,
        edge,
        frame,
        ripple,
        overwrite !== false,
        Boolean(alone),
      );
      editor.change({ op, args, label: t(labelKey) });
    },
    openGate: openGateStretch,
    locateMedia: () => void openLocateMedia(),
    editPlaceholder(placeholder) {
      setState({ placeholderSelected: placeholder.id });
      keyboard.registry.run("placeholder.edit", null, getState());
    },
    wheel: onWheel,
    resized() {
      if (fitWhole && getState().project) fitWholeEdit();
      autoFit(getState());
      if (getState().focusMode) resizeFocus({ animate: false });
      updateLanesScroll(getState());
      overview?.redraw();
    },
  },
});
// A clipboard entry dragged from the Clipboard tab onto the timeline (clipboard-drag.js): outlines
// while dragging, and the drop is one paste (adopted into this project first when it comes from
// another shelf). Esc ends a native drag with dragend, which pastes nothing.
const clipboardDrag = createClipboardDrag({
  getState,
  timeline,
  adopt: (entry, source) =>
    adoptClipboardEntry(entry, source.from, { quiet: true, shelf: source.shelf }),
  paste: (args, entry) =>
    keyboard.sendPlan(
      dropPastePlan(
        { ...entry, id: args.entry_id },
        { at: args.at, targetTracks: args.target_tracks },
        args.mode,
      ),
    ),
});
window.addEventListener("dragover", (event) => void clipboardDrag.over(event));
window.addEventListener("drop", (event) => {
  if (clipboardDrag.active()) void clipboardDrag.drop(event);
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

// Edit | Rendered mix, its banner and the dimmed track controls (render-listen-view.js).
const renderListenView = createRenderListenView({
  t,
  listen: (on) => setRenderListen(on),
  formatWhen: (iso) => renderWhen(iso, formatAbsoluteTime(iso)),
  rate,
  notice: (text) => showNotice(text, "ok"),
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

// The status bar's scope chip (WP83): what the next range operation touches, from the one scope
// function (range-scope.js). A warning tone when no track is selected in selected-only mode.
function updateScopeChip(state) {
  const el = $("scope-chip");
  const chip = scopeChip(state);
  el.hidden = chip === null || !state.project;
  if (el.hidden) return;
  el.classList.toggle("warn", chip.kind === "none");
  el.title = t("ui.scope.chip_title");
  if (chip.kind === "none") {
    el.textContent = t("ui.scope.chip_none");
    return;
  }
  const where = chip.all
    ? t("ui.scope.where_all", { count: chip.count })
    : t("ui.scope.where_some", { names: chip.names.join(", ") });
  el.textContent =
    chip.kind === "range"
      ? t("ui.scope.chip_range", {
          from: frameToTime(chip.start, rate()),
          to: frameToTime(chip.end, rate()),
          where,
        })
      : t("ui.scope.chip_mode", { where });
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
      "focusHeights",
      "focusMode",
      "collapsedBuses",
      "waveformMode",
      "waveformScale",
      "waveformGain",
      "showGates",
      "focusBus",
      "busHeight",
      "groupGap",
      // The silent states and inactive lanes drawn by the waveform layer (SILENCE-VISUALS.md).
      "silencePreview",
      "missingMedia",
      "inactiveStyle",
      "rangeMode",
      "trackSelection",
      "rangeTracks",
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
  if (touched("project", "series")) updateSeriesChip(state);
  if (touched("project", "inPoint", "outPoint")) marksCorner.render(state);
  if (touched("render")) renderListenView.update(state);
  if (touched("project", "words")) updateTabScope();
  if (touched("playing")) {
    if (state.playing) startPlayheadTicker();
    levelMeter.playing(state.playing);
    silencePanel?.playingChanged();
  }
  if (touched("project")) silencePanel?.projectChanged();
  if (touched("playing", "clipboardPlaying")) {
    // A clipboard preview playing: the Play button stops it (transport.toggle).
    const sounding = state.playing || Boolean(state.clipboardPlaying);
    $("play-icon").textContent = sounding ? "■" : "▶";
    $("play-label").textContent = t(sounding ? "ui.transport.stop" : "ui.transport.play");
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
  if (touched("project", "inPoint", "outPoint", "rangeMode", "trackSelection", "rangeTracks"))
    updateScopeChip(state);
  if (touched("waveformMode")) $("waveform-mode").value = state.waveformMode;
  if (
    touched(
      "project",
      "focusTrack",
      "rangeMode",
      "trackSelection",
      "rangeTracks",
      "focusBus",
      "laneHeight",
      "laneHeights",
      "focusHeights",
      "focusMode",
      "collapsedBuses",
      "busHeight",
      "groupGap",
      "loudness",
    )
  )
    trackHeaders.update(state);
  focusChanged(state, touched);
  if (touched("project", "autoFitTracks", "laneHeights", "collapsedBuses", "busHeight", "groupGap"))
    autoFit(state);
  if (
    touched(
      "project",
      "scrollY",
      "laneHeight",
      "laneHeights",
      "focusHeights",
      "collapsedBuses",
      "busHeight",
      "groupGap",
    )
  )
    updateLanesScroll(state);
  if (touched("project", "selection", "focusTrack", "focusBus")) inspector.update(state);
  if (touched("selection", "focusTrack", "focusBus", "focusMode", "panel")) help.update();
  if (
    touched(
      "clipboard",
      "clipboardSelected",
      "clipboardFilter",
      "clipboardKeep",
      "clipboardView",
      "clipboardShared",
      "clipboardSeries",
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
    layoutTabs();
  }
  if (touched("sidebarShown")) {
    document.querySelector(".editor").dataset.sidebar =
      state.sidebarShown === false ? "hidden" : "shown";
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

// View > Language: an explicit choice (kept on the server) beats the browser's language.
let languageChoice = "auto";
try {
  languageChoice = (await api.getLanguage()).setting;
} catch {
  // No answer: follow the browser, as before.
}
setState({ languageChoice });
try {
  setState({ logLevel: (await api.getLogLevel()).level });
} catch {
  // No answer: the menu shows INFO checked, the default.
}
try {
  await initI18n({
    document,
    language: languageChoice === "auto" ? detectLanguage() : languageChoice,
  });
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
  void refreshSeries();
  subscribe(scheduleSeriesRefresh);
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
let pingTimer = null;
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
  onOpen(send) {
    // The playhead clock's offset: a few pings now (the quickest round trip wins), then
    // one now and then.
    for (let i = 0; i < 5; i += 1)
      setTimeout(() => send({ type: "ping", c: performance.now() }), i * 100);
    clearInterval(pingTimer);
    pingTimer = setInterval(() => send({ type: "ping", c: performance.now() }), 10_000);
  },
  onMessage(message) {
    if (message.type === "record") {
      recordView.live(message);
      return;
    }
    if (message.type === "pong") {
      playheadClock.pong(message.c, message.s, performance.now());
      return;
    }
    const result = reduceLive(getState(), message);
    if (result.anchor && playheadClock.accept(result.anchor, performance.now())) {
      setState(anchorPatch(result.anchor));
      if (result.anchor.playing) startPlayheadTicker();
    }
    if (result.preview) previewAnchor(result.preview);
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
