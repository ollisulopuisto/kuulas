// The transcript dock (WP7): the conversation as paragraphs, one per speaker turn.
// Pure parts (paragraphs, windows, selection, the delete and cut plans) live in
// transcript-model.js; this file draws them and listens.
//
// An hour has about 9,000 words, so only the paragraphs in view plus a margin are in
// the DOM (spacers stand for the rest), words have no listeners of their own (the list
// listens, once), and following the playback moves two classes, never re-renders.
import { wordState } from "./focus-words.js";
import { frameToTime } from "./format.js";
import { formatNumber, getLanguage, t } from "./i18n.js";
import { setIcon } from "./icons.js";
import { canShow, removedSummary, statusKey } from "./material-hits.js";
import { canPutBack, commandArgs, describePlan } from "./put-back-model.js";
import { musicNote } from "./transcribable.js";
import {
  currentPosition,
  findMatches,
  firstFrom,
  matchedWords,
  nextMatch,
  prevMatch,
} from "./transcript-find.js";
import { transcriptFollowStep, transcriptPlaybackStep } from "./transcript-follow.js";
import {
  alsoRemovedIndices,
  buildParagraphs,
  collateralBand,
  dragSelection,
  estimateHeight,
  extendTo,
  LOW_CONFIDENCE,
  moveCursor,
  noSelection,
  offsetsOf,
  ownerTracks,
  paragraphOf,
  pauseMarkers,
  pauseSecondsOf,
  placeCursor,
  rightClickPick,
  selectedIndices,
  selectionFrames,
  selectWord,
  shouldLoadWords,
  summaryParts,
  transcribedMedia,
  transcriptEscape,
  visibleRange,
  wordAtTime,
  wordRefs,
} from "./transcript-model.js";
import { anyActive, offerRows } from "./transcript-offer.js";

const MARGIN_PX = 600;
const PREVIEW_DELAY_MS = 120;
const REMOVED_DELAY_MS = 200;
const JOB_POLL_MS = 1000;
const LINE_HEIGHT_EM = 1.85;
const CHAR_EM = 0.52;
const NAVIGATION_KEYS = new Set(["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"]);

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

/**
 * `root`: the dock's <section>. `api`: { getWords, cutPreview, correctWord, transcribe,
 * getJobs }. `actions`: { seek(frame), jump(frame) (a click or a search hit: Follow comes back), showError(error), applyResponse(response) }.
 */
export function createTranscript({ root, getState, setState, api, actions }) {
  // -- the DOM: a list with spacers, an empty state, a follow chip, the pop-up ----------
  const list = el("div", "tx-list");
  const top = el("div", "tx-spacer");
  const rows = el("div", "tx-rows");
  const bottom = el("div", "tx-spacer");
  list.append(top, rows, bottom);
  const empty = el("div", "tx-empty");
  empty.hidden = true;
  const follow = el("button", "button tx-follow");
  follow.type = "button";
  follow.hidden = true;
  const pop = el("div", "tx-pop");
  pop.setAttribute("role", "toolbar");
  pop.hidden = true;
  // The find bar (Mod+F): sticky at the top of the dock, hidden until asked for.
  const findBar = el("div", "tx-find");
  findBar.setAttribute("role", "search");
  findBar.hidden = true;
  const findInput = el("input", "tx-find-input");
  findInput.type = "search";
  findInput.autocomplete = "off";
  findInput.spellcheck = false;
  const findCount = el("span", "tx-find-count");
  findCount.setAttribute("aria-live", "polite");
  // The arrows are icon buttons, the close a ghost icon button like the toast's.
  const findButton = (act, text, kind = "button icon") => {
    const button = el("button", kind, text);
    button.type = "button";
    button.dataset.act = act;
    return button;
  };
  const findPrev = findButton("prev", "↑");
  const findNext = findButton("next", "↓");
  const findClose = findButton("close", "×", "button ghost icon");
  findBar.append(findInput, findCount, findPrev, findNext, findClose);
  // "Not in this edit": the words of the find query the edit does not play (cut, muted,
  // gated, in a recording placed nowhere), from /api/material-search. A closed line until
  // opened; the Transcript itself shows only what is heard.
  const removed = el("div", "tx-removed");
  removed.hidden = true;
  const removedToggle = el("button", "button ghost tx-removed-toggle");
  removedToggle.type = "button";
  const removedList = el("ul", "tx-removed-list");
  removed.append(removedToggle, removedList);
  root.append(findBar, removed, follow, empty, list, pop);
  list.setAttribute("role", "document");

  // -- derived from the words (rebuilt only when they change) -----------------------------
  let words = [];
  let paragraphs = [];
  let pauses = new Map(); // paragraph index -> the silence before it
  let heights = [];
  let offsets = [0];
  const measured = new Map(); // paragraph id -> real height
  let listWidth = 0;
  let fetchedHead = null;
  let fetchedKey = null; // the muted inputs the last fetch was started for
  let fetching = false;
  let lastKey = "";
  // Focus mode (WP28): other speakers' paragraphs are dimmed, or hidden with Alt+F.
  let focusIds = null;
  let hideOthers = false;
  let focusKey = "";
  const paraState = (p) => wordState({ track: p.track }, focusIds, hideOthers);

  // -- what is drawn ---------------------------------------------------------------------------
  const nodes = new Map(); // paragraph index -> element
  const wordNodes = new Map(); // word index -> element
  let now = -1;
  let paused = false;
  let wasPlaying = false;
  let lastSetTop = 0;
  let editing = null;
  let drag = null;
  let previewTimer = 0;
  let previewSeq = 0;
  let previewKey = "";
  let also = new Set();
  let allJobs = [];
  let lastRows = [];
  let jobTimer = 0;
  let findQuery = "";
  let matches = [];
  let found = null; // the current match: its word indices
  let foundWords = new Set(); // every word of every match

  const rate = () => getState().project?.rate ?? 48000;
  const tracksById = () => new Map((getState().project?.tracks ?? []).map((x) => [x.id, x]));
  const nameOfTrack = (id) => {
    const track = tracksById().get(id);
    return track?.speaker || track?.name || id;
  };
  const selection = () => getState().transcriptSelection ?? noSelection();
  const chosen = () => selectedIndices(selection());

  // -- layout ---------------------------------------------------------------------------------
  function sizes() {
    const style = getComputedStyle(list);
    const fontSize = Number.parseFloat(style.getPropertyValue("--text-lg")) || 17;
    const gutter = 172;
    const text = Math.max(200, Math.min(listWidth - gutter, fontSize * CHAR_EM * 62 + 40));
    return {
      charsPerLine: text / (fontSize * CHAR_EM),
      lineHeight: fontSize * LINE_HEIGHT_EM,
      gap: 22,
    };
  }

  function layout() {
    const size = sizes();
    heights = paragraphs.map((p) =>
      paraState(p) === "hidden" ? 0 : (measured.get(p.id) ?? estimateHeight(p, size)),
    );
    offsets = offsetsOf(heights);
  }

  function rebuild() {
    const state = getState();
    const people = state.people ?? {};
    words = state.words ?? [];
    paragraphs = buildParagraphs(words, {
      rate: rate(),
      tracks: state.project?.tracks ?? [],
      people,
      pauseSeconds: pauseSecondsOf(state.pauseBreak),
    });
    pauses = pauseMarkers(words, paragraphs, rate());
    measured.clear();
    listWidth = list.clientWidth || root.clientWidth;
    layout();
    now = -1;
    for (const node of nodes.values()) node.remove();
    nodes.clear();
    wordNodes.clear();
    renderEmptyState();
    renderWindow();
    markNow();
    if (!findBar.hidden) runFind(false);
  }

  // -- the empty state ----------------------------------------------------------------------------
  function transcribeTargets() {
    const project = getState().project;
    if (!project) return [];
    const used = new Set();
    for (const track of project.tracks) {
      if (track.kind === "music") continue;
      for (const clip of track.clips) used.add(clip.media);
    }
    return project.media.filter((item) => used.has(item.id));
  }

  /** The offer: one row per recording without a transcript (transcript-offer.js). */
  function renderEmptyState() {
    const has = words.length > 0;
    list.hidden = !has;
    const targets = transcribeTargets();
    const { rows, all } = offerRows({
      media: targets,
      transcribed: transcribedMedia(getState(), words),
      jobs: allJobs,
    });
    lastRows = rows;
    // A selected clip of a music recording: a plain note, never the transcribe offer.
    const note = musicNote({
      project: getState().project,
      selection: getState().selection,
      transcribed: transcribedMedia(getState(), words),
    });
    empty.hidden = !getState().project || (has && rows.length === 0 && !note);
    empty.replaceChildren();
    if (empty.hidden) return;
    if (note) empty.append(musicNoteBlock(note));
    if (note && rows.length === 0) return;
    if (rows.length === 0) {
      empty.append(el("strong", "", t("ui.transcript.empty")));
      return;
    }
    empty.append(el("strong", "", t("ui.transcript.missing")));
    const table = el("ul", "tx-missing");
    for (const row of rows) table.append(offerRow(row));
    if (all) table.append(offerRow({ all }));
    empty.append(table, el("span", "tx-hint", t("ui.transcript.background")));
    scheduleWindow();
  }

  /** "Music track: not transcribed" with the one explicit way round it (local only: no upload). */
  function musicNoteBlock(note) {
    const block = el("div", "tx-music-note");
    block.append(el("strong", "", t("ui.transcript.music_skipped")));
    const button = offerButton(
      "transcribe-anyway",
      [note.id],
      t("ui.transcript.transcribe_anyway"),
      "play",
      false,
    );
    button.title = t("ui.transcript.transcribe_anyway_title", { name: note.name });
    block.append(button);
    return block;
  }

  function offerButton(act, ids, text, icon, primary) {
    const button = el("button", primary ? "button block primary" : "button block", text);
    button.type = "button";
    button.dataset.act = act;
    button.dataset.ids = ids.join(",");
    return setIcon(button, icon);
  }

  /** A row: the name, what is happening, and the two ways (or the progress of the job). */
  function offerRow(row) {
    const item = el("li", "tx-miss-row");
    const ids = row.all ?? [row.id];
    item.dataset.ids = ids.join(",");
    const name = row.all ? t("ui.transcript.all_files", { count: row.all.length }) : row.name;
    item.append(el("span", "tx-miss-name", name));
    const status = row.all ? "none" : row.status;
    if (status === "queued" || status === "running") {
      const bar = el("progress");
      bar.max = 1;
      bar.value = row.progress;
      bar.setAttribute("aria-label", t("ui.transcript.progress"));
      item.append(el("span", "tx-miss-status", t(`ui.transcript.status.${status}`)));
      if (status === "running") item.append(bar);
      return item;
    }
    item.append(
      el(
        "span",
        status === "failed" ? "tx-miss-status tx-error" : "tx-miss-status",
        status === "failed"
          ? row.error || t("ui.transcript.retry")
          : row.all
            ? ""
            : t("ui.transcript.status.none"),
      ),
    );
    const buttons = el("span", "tx-miss-buttons");
    buttons.append(
      offerButton("transcribe", ids, t("ui.transcript.transcribe"), "play", true),
      offerButton("transcribe-colab", ids, t("ui.transcript.transcribe_colab"), "export", false),
    );
    item.append(buttons);
    return item;
  }

  async function transcribe(onlyIds, { force = false } = {}) {
    const ids = onlyIds ?? transcribeTargets().map((item) => item.id);
    if (ids.length === 0) return;
    try {
      await api.transcribe(ids, { force });
      await refreshJobs();
    } catch (error) {
      actions.showError(error);
    }
  }

  /** Ask /api/jobs and redraw; while a recording waits on a job, ask again until it is done. */
  async function refreshJobs() {
    clearTimeout(jobTimer);
    const before = anyActive(lastRows);
    try {
      allJobs = (await api.getJobs()).jobs;
    } catch {
      // A poll that fails is tried again; the live channel reports the real outcome.
    }
    renderEmptyState();
    if (anyActive(lastRows)) jobTimer = setTimeout(() => void refreshJobs(), JOB_POLL_MS);
    else if (before) void loadWords(true);
  }

  // -- drawing the window --------------------------------------------------------------------------
  function viewTop() {
    return Math.max(0, root.scrollTop - list.offsetTop);
  }

  function firstVisible() {
    const at = viewTop();
    let lo = 0;
    let hi = paragraphs.length - 1;
    let found = 0;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (offsets[mid] <= at) {
        found = mid;
        lo = mid + 1;
      } else hi = mid - 1;
    }
    return found;
  }

  function wordClass(i) {
    const word = words[i];
    const sel = selection();
    const bounds =
      sel.anchor === null
        ? null
        : [Math.min(sel.anchor, sel.cursor), Math.max(sel.anchor, sel.cursor)];
    let name = "w";
    if (word.conf !== undefined && word.conf < LOW_CONFIDENCE) name += " low";
    if (i === now) name += " now";
    if (bounds && i >= bounds[0] && i <= bounds[1]) name += " sel";
    if (i === sel.cursor) name += " cur";
    if (foundWords.has(i)) name += found?.includes(i) ? " find found" : " find";
    if (also.has(i)) name += " also";
    return name;
  }

  /**
   * The silence between two paragraphs of one speaker: a thin line with its length.
   * Clicking selects it as the in/out range. Not a tab stop: the keyboard reaches the
   * same range with the marks and the word cursor.
   */
  function pauseMarker({ start, end, seconds }) {
    const text = t("ui.transcript.pause", { seconds: formatNumber(seconds, { digits: 1 }) });
    const button = el("button", "tx-pause", text);
    button.type = "button";
    button.tabIndex = -1;
    button.dataset.start = String(start);
    button.dataset.end = String(end);
    button.setAttribute(
      "aria-label",
      t("ui.transcript.pause.label", { seconds: formatNumber(seconds, { digits: 1 }) }),
    );
    return button;
  }

  function buildParagraph(index) {
    const p = paragraphs[index];
    const node = el("div", "tx-para");
    node.dataset.p = String(index);
    const focus = paraState(p);
    if (focus !== "normal") node.classList.add(`focus-${focus}`);
    const hue = trackHue(p.track);
    node.style.setProperty("--track-colour", `var(--track-${hue}-edge)`);
    const pause = pauses.get(index);
    if (pause) node.append(pauseMarker(pause));
    const speaker = el("div", "tx-speaker");
    speaker.append(el("b", "", p.name), el("span", "", frameToTime(p.start, rate())));
    const text = el("p", "tx-text");
    for (let i = p.first; i <= p.last; i++) {
      const span = el("span", wordClass(i), `${words[i].w} `);
      span.dataset.i = String(i);
      wordNodes.set(i, span);
      text.append(span);
    }
    node.append(speaker, text);
    return node;
  }

  function trackHue(track) {
    const tracks = getState().project?.tracks ?? [];
    const found = tracks.find((x) => x.id === track);
    if (found?.kind === "music") return 0;
    const speakers = [];
    for (const x of tracks) {
      if (x.kind === "music") continue;
      const key = x.speaker || `track:${x.id}`;
      if (!speakers.includes(key)) speakers.push(key);
    }
    const key = found?.speaker || `track:${track}`;
    return (Math.max(0, speakers.indexOf(key)) % 8) + 1;
  }

  /** Draw the paragraphs near the viewport; keep the ones already drawn. */
  function renderWindow() {
    if (paragraphs.length === 0) {
      top.style.height = "0px";
      bottom.style.height = "0px";
      return;
    }
    const anchor = firstVisible();
    const anchorTop = offsets[anchor];
    const { from, to } = visibleRange(offsets, viewTop(), root.clientHeight, MARGIN_PX);
    for (const [index, node] of nodes) {
      if (index >= from && index < to) continue;
      const p = paragraphs[index];
      for (let i = p.first; i <= p.last; i++) wordNodes.delete(i);
      node.remove();
      nodes.delete(index);
    }
    let after = null;
    for (let index = to - 1; index >= from; index--) {
      let node = nodes.get(index);
      if (!node) {
        node = buildParagraph(index);
        nodes.set(index, node);
        rows.insertBefore(node, after);
      }
      after = node;
    }
    top.style.height = `${offsets[from]}px`;
    bottom.style.height = `${offsets[paragraphs.length] - offsets[to]}px`;
    // Real heights replace the estimates; what changed above the first visible paragraph
    // would shift the text under the reader's eyes, so scroll by that much.
    let changed = false;
    for (const [index, node] of nodes) {
      if (paraState(paragraphs[index]) === "hidden") continue;
      const real = node.offsetHeight + paragraphGap();
      if (Math.abs(real - heights[index]) > 1) {
        measured.set(paragraphs[index].id, real);
        changed = true;
      }
    }
    if (changed) {
      layout();
      top.style.height = `${offsets[from]}px`;
      bottom.style.height = `${offsets[paragraphs.length] - offsets[to]}px`;
      const shift = offsets[anchor] - anchorTop;
      if (shift !== 0) scrollTo(root.scrollTop + shift);
    }
    placePop();
  }

  /** Focus mode changed: redraw the paragraphs near the viewport with their new focus state. */
  function refocus(state) {
    const ids = state.focusMode?.ids ?? null;
    const hide = state.focusHideOthers === true;
    const key = JSON.stringify([ids, hide && ids !== null]);
    if (key === focusKey) return;
    focusKey = key;
    focusIds = ids;
    hideOthers = hide;
    layout();
    for (const node of nodes.values()) node.remove();
    nodes.clear();
    wordNodes.clear();
    renderWindow();
  }

  let gapCache = 0;
  function paragraphGap() {
    if (gapCache) return gapCache;
    const first = rows.firstElementChild;
    gapCache = first ? Number.parseFloat(getComputedStyle(first).marginBottom) || 0 : 0;
    return gapCache;
  }

  function scrollTo(value) {
    const next = Math.max(0, value);
    lastSetTop = next;
    root.scrollTop = next;
  }

  // -- the word under the play cursor and the selection (class changes only) ------------------
  function setClass(i) {
    const node = wordNodes.get(i);
    if (node) node.className = wordClass(i);
  }

  function markNow() {
    const next = wordAtTime(words, getState().playhead ?? 0);
    if (next === now) return false;
    const old = now;
    now = next;
    if (old >= 0) setClass(old);
    if (next >= 0) setClass(next);
    return true;
  }

  let marked = new Set();
  function markSelection() {
    const next = new Set(chosen());
    if (selection().cursor >= 0) next.add(selection().cursor);
    for (const i of also) next.add(i);
    for (const i of marked) setClass(i);
    for (const i of next) setClass(i);
    marked = next;
  }

  // -- following the playback ----------------------------------------------------------------------
  function wordRect(i) {
    const node = wordNodes.get(i);
    if (!node) return null;
    const box = node.getBoundingClientRect();
    const frame = root.getBoundingClientRect();
    return { top: box.top - frame.top, bottom: box.bottom - frame.top };
  }

  /** Scroll so word `i` is in view; `place` puts it a third of the way down. */
  function reveal(i, { place = false } = {}) {
    if (i < 0 || paragraphs.length === 0) return;
    const p = paragraphOf(paragraphs, i);
    if (p < 0) return;
    let rect = wordRect(i);
    const header = list.offsetTop;
    if (!rect) {
      scrollTo(header + offsets[p] - root.clientHeight / 3);
      renderWindow();
      rect = wordRect(i);
    }
    if (!rect) return;
    const low = header + 8;
    const high = root.clientHeight - 24;
    if (place || rect.top < low || rect.bottom > high) {
      scrollTo(root.scrollTop + rect.top - root.clientHeight / 3);
      renderWindow();
    }
  }

  function followPlayback() {
    const state = getState();
    if (!state.playing || words.length === 0) return;
    if (paused) return;
    if (now >= 0) reveal(now);
  }

  function setPaused(value) {
    paused = value;
    follow.hidden = !(paused && getState().playing);
    follow.textContent = t("ui.transcript.follow");
  }

  root.addEventListener("scroll", () => {
    if (Math.abs(root.scrollTop - lastSetTop) > 2) {
      setPaused(
        transcriptFollowStep({ paused, playing: getState().playing }, { type: "manual-scroll" })
          .paused,
      );
    }
    lastSetTop = root.scrollTop;
    scheduleWindow();
  });
  let windowQueued = false;
  function scheduleWindow() {
    if (windowQueued) return;
    windowQueued = true;
    requestAnimationFrame(() => {
      windowQueued = false;
      renderWindow();
    });
  }
  follow.addEventListener("click", () => {
    setPaused(
      transcriptFollowStep({ paused, playing: getState().playing }, { type: "follow" }).paused,
    );
    followPlayback();
  });

  // -- pointer: click, shift-click, drag, double-click (one set of listeners) ------------------------
  const wordAt = (event) => {
    const node = document.elementFromPoint(event.clientX, event.clientY)?.closest?.(".w");
    return node && list.contains(node) ? Number(node.dataset.i) : -1;
  };

  list.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || editing) return;
    const i = wordAt(event);
    if (i < 0) return;
    root.focus({ preventScroll: true });
    if (event.shiftKey) {
      setState({ transcriptSelection: extendTo(selection(), i) });
      return;
    }
    drag = { from: i, moved: false };
    list.setPointerCapture(event.pointerId);
  });
  list.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const i = wordAt(event);
    if (i < 0 || (i === drag.from && !drag.moved)) return;
    drag.moved = true;
    setState({ transcriptSelection: dragSelection(drag.from, i) });
  });
  list.addEventListener("pointerup", (event) => {
    if (!drag) return;
    const { from, moved } = drag;
    drag = null;
    if (list.hasPointerCapture(event.pointerId)) list.releasePointerCapture(event.pointerId);
    if (moved) return;
    // A click: the cursor and the play cursor go to the word.
    setState({ transcriptSelection: placeCursor(from) });
    setPaused(false);
    actions.jump(words[from].s);
  });
  list.addEventListener("click", (event) => {
    const marker = event.target.closest?.(".tx-pause");
    if (!marker || !list.contains(marker)) return;
    // The app has no range selection of its own; the in/out marks are the range.
    setState({ inPoint: Number(marker.dataset.start), outPoint: Number(marker.dataset.end) });
    actions.jump(Number(marker.dataset.start));
  });
  list.addEventListener("dblclick", (event) => {
    const i = wordAt(event);
    if (i >= 0) setState({ transcriptSelection: selectWord(i) });
  });

  // -- keyboard: the word cursor ---------------------------------------------------------------------
  root.addEventListener("keydown", (event) => {
    if (editing || event.target !== root) return;
    // A word range collapses and Esc stops there; the next Esc is the normal escape order.
    if (transcriptEscape(event, selection(), (next) => setState({ transcriptSelection: next }))) {
      return;
    }
    if (!NAVIGATION_KEYS.has(event.key) || event.metaKey || event.ctrlKey || event.altKey) return;
    if (words.length === 0) return;
    event.preventDefault();
    const sel = selection();
    const to = moveCursor(sel.cursor, event.key, { count: words.length, paragraphs });
    if (event.shiftKey) {
      setState({ transcriptSelection: extendTo(sel.cursor < 0 ? placeCursor(to) : sel, to) });
    } else {
      setState({ transcriptSelection: placeCursor(to) });
      actions.seek(words[to].s);
    }
    setPaused(false);
    reveal(to);
  });
  // Right-click on a word: the picked words if it is one of them, else that word becomes the
  // pick; the menu then offers what can be done with them. Over no word with nothing picked
  // the browser's own menu is left alone.
  root.addEventListener("contextmenu", (event) => {
    if (editing) return;
    const next = rightClickPick(selection(), wordAt(event));
    if (next === null) return;
    if (next !== selection()) setState({ transcriptSelection: next });
    actions.contextMenu?.(event);
  });
  root.addEventListener("wheel", () => {
    if (!paused) setPaused(true);
  });
  root.addEventListener("touchmove", () => {
    if (!paused) setPaused(true);
  });
  empty.addEventListener("click", (event) => {
    const button = event.target.closest?.("button[data-act]");
    if (!button) return;
    const ids = (button.dataset.ids ?? "").split(",").filter(Boolean);
    if (button.dataset.act === "transcribe") void transcribe(ids);
    else if (button.dataset.act === "transcribe-anyway") void transcribe(ids, { force: true });
    else if (button.dataset.act === "transcribe-colab") actions.transcribeColab?.(ids);
  });

  // -- the pop-up over the selection ----------------------------------------------------------------
  function popAction(label, key, act, title) {
    const button = el("button", "button keyed");
    button.type = "button";
    button.dataset.act = act;
    button.title = title;
    button.append(el("span", "", label), el("kbd", "", key));
    return button;
  }

  function renderPop() {
    const picked = chosen();
    if (picked.length === 0 || editing) {
      pop.hidden = true;
      return;
    }
    const owners = ownerTracks(words, picked).map(nameOfTrack);
    const who = new Intl.ListFormat(getLanguage(), { type: "conjunction" }).format(owners);
    const summary = el("div", "tx-sum");
    summary.setAttribute("aria-live", "polite");
    const preview = getState().cutPreview;
    const parts = summaryParts(preview, { rate: rate(), nameOf: nameOfTrack });
    if (!preview) summary.textContent = "";
    else if (parts.length === 0) {
      summary.classList.add("none");
      summary.textContent = t("ui.transcript.sum.none");
    } else {
      const text = parts.map((part) =>
        part.words > 0
          ? t("ui.transcript.sum.words", { count: part.words, name: part.name })
          : t("ui.transcript.sum.audio", {
              seconds: part.seconds.toFixed(1).replace(".", getLanguage() === "fi" ? "," : "."),
              name: part.name,
            }),
      );
      summary.textContent = t("ui.transcript.sum.also", {
        list: new Intl.ListFormat(getLanguage(), { type: "conjunction" }).format(text),
      });
    }
    const acts = el("div", "tx-acts");
    acts.append(
      popAction(
        t("ui.transcript.pop.delete", { name: who }),
        "⌫",
        "delete",
        t("ui.transcript.pop.delete_title"),
      ),
      popAction(t("ui.transcript.pop.cut"), "X", "cut", t("ui.transcript.pop.cut_title")),
    );
    const correct = popAction(
      t("ui.transcript.pop.correct"),
      "Enter",
      "correct",
      t("ui.transcript.pop.correct_title"),
    );
    correct.disabled = picked.length !== 1;
    acts.append(correct);
    pop.replaceChildren(summary, acts);
    pop.setAttribute("aria-label", t("ui.transcript.pop.label"));
    pop.hidden = false;
    placePop();
  }

  function placePop() {
    if (pop.hidden) return;
    const picked = chosen();
    if (picked.length === 0) return;
    const frame = root.getBoundingClientRect();
    const node = wordNodes.get(picked[0]);
    let x = 12;
    let y;
    if (node) {
      const box = node.getBoundingClientRect();
      x = box.left - frame.left + root.scrollLeft;
      y = box.top - frame.top + root.scrollTop;
    } else {
      const p = paragraphOf(paragraphs, picked[0]);
      y = list.offsetTop + (offsets[p] ?? 0);
    }
    const height = pop.offsetHeight;
    const above = y - height - 8;
    pop.style.left = `${Math.max(8, Math.min(x, root.clientWidth - pop.offsetWidth - 8))}px`;
    pop.style.top = `${above < root.scrollTop + 40 ? y + 32 : above}px`;
  }

  pop.addEventListener("click", (event) => {
    const act = event.target.closest?.("[data-act]")?.dataset.act;
    if (act === "delete") actions.run("transcript.delete_words");
    else if (act === "cut") actions.run("transcript.cut_words");
    else if (act === "correct") actions.run("transcript.correct");
  });
  pop.addEventListener("pointerdown", (event) => event.preventDefault());

  // -- the crosstalk preview ---------------------------------------------------------------------------
  function schedulePreview() {
    clearTimeout(previewTimer);
    const picked = chosen();
    const key = picked.join(",");
    if (picked.length === 0) {
      previewSeq++;
      previewKey = "";
      also = new Set();
      if (getState().cutPreview || getState().collateral)
        setState({ cutPreview: null, collateral: null });
      return;
    }
    if (key === previewKey) return;
    previewTimer = setTimeout(async () => {
      const seq = ++previewSeq;
      const state = getState();
      if (state.wordsHead !== state.head) return;
      try {
        const preview = await api.cutPreview(wordRefs(words, picked));
        if (seq !== previewSeq) return;
        previewKey = key;
        also = alsoRemovedIndices(words, preview);
        setState({ cutPreview: preview, collateral: collateralBand(preview) });
      } catch {
        // A stale selection names no word; the pop-up then shows no summary.
        if (seq === previewSeq) setState({ cutPreview: null, collateral: null });
      }
    }, PREVIEW_DELAY_MS);
  }

  // -- correcting a word ----------------------------------------------------------------------------------
  function startCorrect() {
    const sel = selection();
    const picked = chosen();
    const i = picked.length === 1 ? picked[0] : picked.length === 0 ? sel.cursor : -1;
    const node = wordNodes.get(i);
    if (i < 0 || !node) return false;
    const word = words[i];
    const input = el("input", "tx-edit");
    input.type = "text";
    input.value = word.w;
    input.size = Math.max(3, word.w.length + 1);
    input.setAttribute("aria-label", t("ui.transcript.pop.correct"));
    editing = { i, node };
    renderPop();
    node.replaceChildren(input);
    input.focus();
    input.select();
    const finish = (save) => {
      if (!editing) return;
      editing = null;
      const text = input.value.trim();
      node.textContent = `${word.w} `;
      root.focus({ preventScroll: true });
      renderPop();
      if (save && text && text !== word.w) {
        api
          .correctWord(word.media, word.index, text)
          .then((response) => actions.applyResponse(response))
          .catch(actions.showError);
      }
    };
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        finish(true);
      } else if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        finish(false);
      }
    });
    input.addEventListener("blur", () => finish(false));
    return true;
  }

  // -- find (Mod+F): over the words, never the DOM, so it spans the whole virtual list ------------
  function paintFind(before) {
    foundWords = matchedWords(matches);
    for (const i of new Set([...before, ...foundWords])) setClass(i);
    const label = t("ui.find.label");
    findInput.placeholder = t("ui.find.placeholder");
    findInput.setAttribute("aria-label", label);
    findBar.setAttribute("aria-label", label);
    findPrev.title = findPrev.ariaLabel = t("ui.find.previous");
    findNext.title = findNext.ariaLabel = t("ui.find.next");
    findClose.title = findClose.ariaLabel = t("ui.find.close");
    const { n, m } = currentPosition(matches, found);
    if (findQuery.trim() === "") findCount.textContent = "";
    else findCount.textContent = m === 0 ? t("ui.find.none") : t("ui.find.count", { n, m });
    findPrev.disabled = findNext.disabled = m === 0;
  }

  // -- not in this edit ------------------------------------------------------------------------------
  let removedHits = [];
  let removedOpen = false;
  let removedAsk = 0; // the newest request: an older answer is dropped
  let removedTimer = 0;

  // The open "put back" preview: { index (into removedHits), plan, scope }.
  let putBack = null;

  /** The preview under a hit: what comes back, where, what moves, what each track gets. */
  function putBackBlock() {
    const view = describePlan(putBack.plan, { rate: rate(), nameOf: nameOfTrack });
    const seconds = (value) => formatNumber(value, { digits: 1 });
    const time = (frame) => frameToTime(frame, rate());
    const box = el("div", "tx-putback");
    box.append(
      el("strong", "", t("ui.putback.what", { text: view.text, seconds: seconds(view.seconds) })),
    );
    const lines = el("ul", "tx-putback-lines");
    const line = (text) => lines.append(el("li", "", text));
    if (view.canConfirm) line(t(view.place.key, { time: time(view.place.frame) }));
    else line(`${t(view.place.key)} ${view.candidates.map(time).join(" · ")}`.trim());
    if (view.push) {
      line(
        t("ui.putback.pushes", {
          time: time(view.push.frame),
          seconds: seconds(view.push.seconds),
          count: view.push.count,
        }),
      );
    }
    for (const track of view.tracks) line(`${track.name}: ${t(track.key)}`);
    const buttons = el("div", "tx-putback-buttons");
    const button = (act, text, kind = "button") => {
      const node = el("button", kind, text);
      node.type = "button";
      node.dataset.act = act;
      return node;
    };
    const confirm = button("putback-confirm", t("ui.putback.confirm"), "button primary");
    confirm.disabled = !view.canConfirm;
    buttons.append(
      button("putback-cancel", t("ui.putback.cancel")),
      button("putback-playhead", t("ui.putback.at_playhead")),
      confirm,
    );
    box.append(lines, buttons);
    return box;
  }

  async function openPutBack(index) {
    const hit = removedHits[index];
    const scope = actions.scopeTracks?.();
    if (!hit || scope === null) return;
    try {
      const plan = await api.putBackPlan({
        media: hit.media,
        first: hit.first,
        last: hit.last,
        track_ids: scope,
      });
      putBack = { index, plan, scope };
      paintRemoved();
      removedList
        .querySelector('[data-act="putback-confirm"]:not(:disabled), [data-act="putback-playhead"]')
        ?.focus();
    } catch (error) {
      actions.showError(error);
    }
  }

  /** Do it: at the seam the plan found, or at the playhead when that was chosen. */
  async function confirmPutBack(atPlayhead) {
    if (!putBack) return;
    const { index, plan, scope } = putBack;
    const hit = removedHits[index];
    const at = atPlayhead ? Math.round(getState().playhead ?? 0) : null;
    try {
      const response = await api.command("put_back", commandArgs(hit.media, plan, scope, at));
      putBack = null;
      actions.applyResponse(response);
      actions.jump(at ?? plan.at);
    } catch (error) {
      actions.showError(error);
    }
  }

  function paintRemoved() {
    const summary = removedSummary(removedHits.length);
    removed.hidden = findBar.hidden || summary === null;
    if (removed.hidden) return;
    removedToggle.textContent = `${removedOpen ? "▾" : "▸"} ${t(summary.key, summary.values)}`;
    removedToggle.setAttribute("aria-expanded", String(removedOpen));
    removedList.hidden = !removedOpen;
    removedList.setAttribute("aria-label", t("ui.find.removed.label"));
    removedList.replaceChildren();
    if (!removedOpen) return;
    removedHits.forEach((hit, i) => {
      const row = el("li", "tx-removed-row");
      const tag = el("span", `tx-tag ${hit.status}`, t(statusKey(hit.status)));
      const who = el("span", "tx-removed-who", hit.spk || "");
      const quote = el("span", "tx-removed-quote");
      quote.append(`${hit.before} `.trimStart(), el("strong", "", hit.match), ` ${hit.after}`);
      row.append(tag, who, quote);
      if (canShow(hit)) {
        const show = el("button", "button ghost", t("ui.find.removed.show"));
        show.type = "button";
        show.title = t("ui.find.removed.show_title");
        show.dataset.hit = String(i);
        row.append(show);
      }
      if (canPutBack(hit)) {
        const back = el("button", "button ghost", t("ui.find.removed.put_back"));
        back.type = "button";
        back.title = t("ui.find.removed.put_back_title");
        back.dataset.act = "putback-open";
        back.dataset.hit = String(i);
        row.append(back);
      }
      if (putBack?.index === i) row.append(putBackBlock());
      removedList.append(row);
    });
  }

  /** Ask the server for the hits outside the edit, a moment after the last keystroke. */
  function loadRemoved() {
    clearTimeout(removedTimer);
    const query = findQuery.trim();
    const ask = ++removedAsk;
    if (query === "" || findBar.hidden) {
      removedHits = [];
      paintRemoved();
      return;
    }
    removedTimer = setTimeout(async () => {
      let hits = [];
      try {
        hits = (await api.searchMaterial(query)).hits ?? [];
      } catch (error) {
        actions.showError(error);
      }
      if (ask !== removedAsk) return;
      removedHits = hits;
      putBack = null; // the hits changed under it
      paintRemoved();
    }, REMOVED_DELAY_MS);
  }

  removed.addEventListener("click", (event) => {
    if (event.target.closest(".tx-removed-toggle")) {
      removedOpen = !removedOpen;
      paintRemoved();
      return;
    }
    const act = event.target.closest("[data-act]")?.dataset.act;
    if (act === "putback-open")
      void openPutBack(Number(event.target.closest("[data-hit]").dataset.hit));
    else if (act === "putback-confirm") void confirmPutBack(false);
    else if (act === "putback-playhead") void confirmPutBack(true);
    else if (act === "putback-cancel") {
      putBack = null;
      paintRemoved();
    }
    if (act) return;
    const at = event.target.closest("[data-hit]")?.dataset.hit;
    const hit = at === undefined ? null : removedHits[Number(at)];
    if (hit && canShow(hit)) actions.jump(hit.at);
  });
  // Esc closes the preview first (a layer at a time), and does nothing else.
  removed.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !putBack) return;
    event.preventDefault();
    event.stopPropagation();
    putBack = null;
    paintRemoved();
  });

  function goToMatch(match) {
    const before = foundWords;
    found = match;
    paintFind(before);
    if (!match) return;
    setState({ transcriptSelection: placeCursor(match[0]) });
    setPaused(false);
    actions.jump(words[match[0]].s);
    reveal(match[0], { place: true });
  }

  /** Search again (the query or the words changed); `jump` goes to the first match from here. */
  function runFind(jump) {
    const before = foundWords;
    matches = findMatches(words, findQuery);
    const from = now >= 0 ? now : Math.max(0, selection().cursor);
    found = firstFrom(matches, from);
    if (jump) goToMatch(found);
    else paintFind(before);
    loadRemoved();
  }

  function stepFind(direction) {
    if (matches.length === 0) return;
    const from = found ? found[0] : now;
    goToMatch(direction > 0 ? nextMatch(matches, from) : prevMatch(matches, from));
  }

  function openFind(options = {}) {
    if (options.removed) removedOpen = true;
    findBar.hidden = false;
    findInput.focus();
    findInput.select();
    runFind(false);
  }

  function closeFind() {
    findBar.hidden = true;
    const before = foundWords;
    findQuery = "";
    findInput.value = "";
    matches = [];
    found = null;
    paintFind(before);
    loadRemoved();
    root.focus({ preventScroll: true });
  }

  findInput.addEventListener("input", () => {
    findQuery = findInput.value;
    runFind(true);
  });
  findInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      stepFind(event.shiftKey ? -1 : 1);
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeFind();
    }
  });
  findBar.addEventListener("click", (event) => {
    const act = event.target.closest?.("[data-act]")?.dataset.act;
    if (act === "next") stepFind(1);
    else if (act === "prev") stepFind(-1);
    else if (act === "close") closeFind();
  });

  // -- loading the words ---------------------------------------------------------------------------------
  /** The words are derived from the edit: after any change of head, ask again. */
  async function loadWords(force = false) {
    const { head, serverMutedKey: key } = getState();
    if (!shouldLoadWords({ head, key, fetchedHead, fetchedKey, fetching, force })) return;
    fetching = true;
    let ok = false;
    try {
      const body = await api.getWords();
      fetchedHead = head;
      fetchedKey = key;
      ok = true;
      const sel = selection();
      setState({
        words: body.words ?? [],
        transcribed: body.transcribed ?? [],
        people: body.people ?? {},
        wordsHead: head,
        // The old indices mean other words now: keep the place, drop the selection.
        transcriptSelection: placeCursor(Math.min(sel.cursor, (body.words?.length ?? 0) - 1)),
        cutPreview: null,
        collateral: null,
      });
    } catch (error) {
      actions.showError(error);
    } finally {
      fetching = false;
      // The edit moved on while this was in flight (head, or the mute/solo inputs under
      // the same head): ask again. Not after a failure, or a dead server loops.
      if (ok) void loadWords();
    }
  }

  // -- state changes ---------------------------------------------------------------------------------------
  const observer = new ResizeObserver(() => {
    const width = list.clientWidth || root.clientWidth;
    if (Math.abs(width - listWidth) < 2) {
      scheduleWindow();
      return;
    }
    listWidth = width;
    measured.clear();
    layout();
    scheduleWindow();
  });
  observer.observe(root);

  return {
    /** Called by app.js with every state change (and the patch, or null for "all"). */
    update(state, patch) {
      const changed = patch ? new Set(Object.keys(patch)) : null;
      const touched = (...names) => changed === null || names.some((name) => changed.has(name));
      const playback = transcriptPlaybackStep({ paused, wasPlaying }, state.playing);
      wasPlaying = playback.wasPlaying;
      if (playback.paused !== paused) setPaused(playback.paused);
      if (touched("head", "serverMutedKey")) void loadWords();
      if (touched("focusMode", "focusHideOthers")) refocus(state);
      const key = `${state.wordsHead}|${state.words?.length}|${state.project?.rate}|${state.project?.tracks?.map((x) => x.id + x.speaker + x.name).join()}|${JSON.stringify(state.people ?? {})}|${state.pauseBreak}`;
      if (state.words !== words || key !== lastKey) {
        lastKey = key;
        rebuild();
      }
      if (
        touched("project") &&
        !changed?.has("words") &&
        (lastRows.length > 0 || words.length === 0)
      )
        void refreshJobs();
      if (touched("playhead", "playing")) {
        if (touched("playing") && !state.playing) follow.hidden = true;
        markNow();
        followPlayback();
      }
      if (touched("transcriptSelection")) {
        // Selecting words also marks them on the timeline, where the edges can be fine-tuned.
        const marks = selectionFrames(words, selection());
        if (marks) setState(marks);
        markSelection();
        renderPop();
        schedulePreview();
      }
      if (touched("cutPreview")) {
        markSelection();
        renderPop();
      }
    },
    startCorrect,
    openFind,
    transcribe,
    /** Look at the background jobs again (a job was started elsewhere, e.g. on Colab). */
    refreshJobs,
    /** The recordings the Transcribe buttons would take: every speech track's. */
    targetIds: () => transcribeTargets().map((item) => item.id),
    /** The word indices Backspace and X act on. */
    chosen,
    reveal,
  };
}
