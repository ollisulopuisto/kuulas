// The History tab (WP8): the steps of the edit, newest first, in pages as you scroll.
// Session markers are thin dividers and the current step is highlighted. Steps that are not
// part of the current state are grouped by why, each kind with an icon and a word (never
// colour alone): Undone (Redo brings them back; open), Rolled back (a Restore skipped them;
// closed) and Left behind (an edit after an undo; closed). A restore row says what it went
// back to, its target carries a "restore point" tag, and a bracket in the left margin joins
// the two. Repeated steps on one object show as one row. A click picks a step; Restore
// (Enter) adds a new step equal to it and loses nothing. Right/Left open and close a group
// or run; G goes from a restore row to its restore point. The logic is history-model.js's;
// what Restore does is app.js's (actions.restore).

import {
  currentStep,
  emptyKey,
  expandAllMap,
  historyRows,
  mergePage,
  moveRow,
  needsMore,
  restorePointOf,
  selectionAfterLoad,
  visibleNodes,
} from "./history-model.js";
import { formatAbsoluteTime, getLanguage, onLanguageChange, t } from "./i18n.js";
import { ICONS } from "./icons.js";

const SAVED_KEY = "kuulas.history.savedOnly";

// The "Saved versions" choice is the user's, not the project's: remembered in this browser.
function readSavedOnly() {
  try {
    return globalThis.localStorage?.getItem(SAVED_KEY) === "1";
  } catch {
    return false;
  }
}
function writeSavedOnly(on) {
  try {
    globalThis.localStorage?.setItem(SAVED_KEY, on ? "1" : "0");
  } catch {
    // blocked storage: the choice lasts for this session only
  }
}

const bookmark = () => {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "pin");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", ICONS.bookmark);
  svg.append(path);
  return svg;
};

const PAGE = 100;
const PAGE_MAX = 500; // the server's limit per request
// The icon each kind of step carries beside its word (sketches: History Restore Sketches).
const DIM_ICON = { undone: "↶", rolled_back: "↩", left_behind: "⑂" };
const RESTORE_ICON = "⤺";

const el = (tag, props = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "class") node.className = value;
    else if (key in node) node[key] = value;
    else node.setAttribute(key, value);
  }
  node.append(...children);
  return node;
};
const icon = (text) => el("span", { class: "ico", textContent: text, "aria-hidden": "true" });

/**
 * `api.getHistory({ limit, before, saved })` answers { nodes, more }; `actions.restore(id)`,
 * `actions.undo()`, `actions.redo()`, `actions.renameVersion(id, name)` (a promise),
 * `actions.showError(error)`. `now()` is the clock (tests and the page differ).
 */
export function createHistoryPanel({
  root,
  api,
  getState,
  setState,
  actions,
  now = () => Date.now(),
}) {
  let nodes = [];
  let more = false;
  let loading = false;
  let loadedHead; // the head the list was fetched at; undefined: never
  let requestedHead; // the head a fetch was started for
  let loadedLanguage; // names are made by the server in the language of the request
  let token = 0;
  let signature = "";
  let savedOnly = readSavedOnly();
  let query = "";
  let renaming = null; // the id of the saved version being renamed
  let expanded = {}; // group and run ids the user opened (true) or closed (false)
  let rows = []; // what is drawn, from history-model.js historyRows
  const rowEls = new Map(); // id -> the drawn row

  const list = el("ul", {
    class: "hist",
    role: "listbox",
    "aria-label": t("ui.history.list_label"),
  });
  const brackets = el("div", { class: "hist-brackets", "aria-hidden": "true" });
  const scroller = el("div", { class: "hist-scroll" }, list, brackets);
  const status = el("p", { class: "hint", hidden: true });
  const older = el("button", {
    type: "button",
    class: "button block",
    "data-icon": "older",
    hidden: true,
  });
  const restore = el("button", {
    type: "button",
    class: "button block primary",
    "data-icon": "restore",
  });
  const hint = el("span", { class: "hint" });
  // The one action bar, at the top (owner, 2026-10-19). Undo and Redo left the header; the
  // same two commands are in the Edit menu with their keys.
  const undo = el("button", { type: "button", class: "button block", "data-icon": "undo" });
  const redo = el("button", { type: "button", class: "button block", "data-icon": "redo" });
  const bar = el("div", { class: "actionbar", role: "group" }, undo, redo, restore, hint);
  const title = el("h2");
  const showAll = el("button", {
    type: "button",
    class: "button hist-seg",
    dataset: { filter: "all" },
  });
  const showSaved = el("button", {
    type: "button",
    class: "button hist-seg",
    dataset: { filter: "saved" },
  });
  // One two-state switch (owner, 2026-10-21): two joined segments, the active one filled.
  const filterGroup = el("div", { class: "hist-filter", role: "group" }, showAll, showSaved);
  // While only saved versions show, say that any step can be restored (File > Open earlier
  // version lands here with the filter on), with a way straight back to All steps.
  const savedHintText = el("span");
  const savedHintLink = el("button", { type: "button", class: "button ghost hist-link" });
  const savedHint = el(
    "p",
    { class: "hist-saved-hint", hidden: true },
    savedHintText,
    " ",
    savedHintLink,
  );
  const search = el("input", { type: "search", class: "hist-search" });
  root.replaceChildren(title, bar, filterGroup, savedHint, search, status, scroller, older);

  function setSavedOnly(on) {
    if (on === savedOnly) return;
    savedOnly = on;
    writeSavedOnly(on);
    // The server pages the saved versions alone, so the list is fetched again.
    nodes = [];
    more = false;
    loadedHead = undefined;
    requestedHead = undefined;
    signature = "";
    const head = getState().head;
    if (head) {
      requestedHead = head;
      void reload(head);
    }
    draw();
  }
  showAll.addEventListener("click", () => setSavedOnly(false));
  showSaved.addEventListener("click", () => setSavedOnly(true));
  savedHintLink.addEventListener("click", () => {
    setSavedOnly(false);
    showAll.focus();
  });
  search.addEventListener("input", () => {
    query = search.value;
    signature = "";
    draw();
  });
  search.addEventListener("keydown", (event) => event.stopPropagation());

  async function fetchPage(before, limit) {
    const page = await api.getHistory({ limit, before, saved: savedOnly });
    return { nodes: page.nodes ?? [], more: Boolean(page.more) };
  }

  /** Fetch again from the top, as many steps as are on screen: undo moves the head, which
   * changes which steps are past, redo or abandoned all the way down. */
  async function reload(head) {
    const mine = ++token;
    loading = true;
    draw();
    try {
      let fetched = [];
      let cursor = null;
      let left = Math.max(nodes.length, PAGE);
      let hasMore = false;
      const language = getLanguage();
      while (left > 0) {
        const page = await fetchPage(cursor, Math.min(PAGE_MAX, left));
        if (mine !== token) return;
        fetched = fetched.concat(page.nodes);
        hasMore = page.more;
        if (!page.more || page.nodes.length === 0) break;
        cursor = page.nodes[page.nodes.length - 1].id;
        left -= page.nodes.length;
      }
      nodes = fetched;
      more = hasMore;
      loadedHead = head;
      loadedLanguage = language;
      setState({ historyCurrent: currentStep(nodes, head) });
      pick(selectionAfterLoad(getState().historySelected, nodes, head));
    } catch (error) {
      if (mine === token) actions.showError(error);
    } finally {
      if (mine === token) {
        loading = false;
        draw();
        fillIfShort();
      }
    }
  }

  async function loadMore() {
    if (loading || !more || nodes.length === 0) return;
    const mine = ++token;
    loading = true;
    draw();
    try {
      const page = await fetchPage(nodes[nodes.length - 1].id, PAGE);
      if (mine !== token) return;
      nodes = mergePage(nodes, page.nodes);
      more = page.more;
    } catch (error) {
      if (mine === token) actions.showError(error);
    } finally {
      if (mine === token) {
        loading = false;
        draw();
        fillIfShort();
      }
    }
  }

  const wantsMore = () =>
    needsMore({
      scrollTop: scroller.scrollTop,
      clientHeight: scroller.clientHeight,
      scrollHeight: scroller.scrollHeight,
      more,
      loading,
    });
  // A list that does not fill the panel cannot be scrolled to ask for more.
  const fillIfShort = () => {
    if (!root.hidden && scroller.clientHeight > 0 && wantsMore()) void loadMore();
  };
  scroller.addEventListener("scroll", () => {
    if (wantsMore()) void loadMore();
  });
  older.addEventListener("click", () => void loadMore());

  /** Pick a row; "Go to restore point" is offered while the pick is a restore step. */
  function pick(id) {
    const state = getState();
    const target = restorePointOf(nodes, id);
    const patch = {};
    if (state.historySelected !== id) patch.historySelected = id;
    if ((state.historyRestoreTarget ?? null) !== target) patch.historyRestoreTarget = target;
    if (Object.keys(patch).length > 0) setState(patch);
  }

  const rowOf = (id) => rowEls.get(id) ?? null;

  function focusRow(id) {
    pick(id);
    draw();
    const node = rowOf(id);
    node?.focus();
    node?.scrollIntoView?.({ block: "nearest" });
  }

  function setOpen(id, open) {
    expanded = { ...expanded, [id]: open };
    signature = "";
    draw();
  }

  function nameInput(row) {
    const input = el("input", {
      type: "text",
      class: "hist-rename",
      value: row.saved.name,
      "aria-label": t("ui.history.rename_label"),
    });
    let done = false;
    const finish = (commit) => {
      if (done) return;
      done = true;
      renaming = null;
      signature = "";
      const name = input.value.trim();
      if (commit && name && name !== row.saved.name) {
        void actions.renameVersion(row.id, name).then(() => reload(getState().head));
      } else {
        draw();
      }
    };
    input.addEventListener("keydown", (event) => {
      event.stopPropagation();
      if (event.key === "Enter") finish(true);
      else if (event.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
    input.addEventListener("click", (event) => event.stopPropagation());
    queueMicrotask(() => {
      input.focus();
      input.select();
    });
    return input;
  }

  function groupRow(row, selected) {
    const tip = t("ui.history.group.title", { text: row.text });
    const node = el(
      "li",
      {
        class: `hist-group dim-${row.group}`,
        role: "option",
        id: `hist-${row.id}`,
        tabIndex: selected ? 0 : -1,
        title: tip,
        "aria-selected": String(selected),
        "aria-expanded": String(row.expanded),
        "aria-description": row.dimText,
        dataset: { id: row.id },
      },
      el("span", { class: "chev", textContent: row.expanded ? "▾" : "▸", "aria-hidden": "true" }),
      icon(DIM_ICON[row.group]),
      el("span", { class: "lab", textContent: row.text }),
      el("span", { class: "t", textContent: row.time }),
    );
    node.addEventListener("click", () => {
      pick(row.id);
      setOpen(row.id, !row.expanded);
      rowOf(row.id)?.focus();
    });
    return node;
  }

  function stepRow(row, selected) {
    const classes = ["hist-step"];
    if (row.saved) classes.push("saved");
    if (row.head) classes.push("head");
    if (row.dim) classes.push("future", `dim-${row.dim}`);
    if (row.parent) classes.push("child");
    if (row.run) classes.push("run");
    const stateText = row.head ? t("ui.history.head_title") : row.dimText || row.stands;
    const savedText = row.saved
      ? t("ui.history.saved_title", { kind: row.saved.kindLabel, name: row.saved.name })
      : "";
    const runText = row.run ? t("ui.history.run_title", { count: row.run.count }) : "";
    const tip = [savedText, formatAbsoluteTime(row.created), stateText, runText]
      .filter(Boolean)
      .join(" · ");
    const lead = row.dim ? icon(DIM_ICON[row.dim]) : row.restoreTarget ? icon(RESTORE_ICON) : "";
    const tags = [];
    if (row.restorePoint) {
      tags.push(
        el("span", {
          class: "tag pt",
          textContent: `${RESTORE_ICON} ${t("ui.history.restore_point")}`,
          title: t("ui.history.restore_point_title"),
        }),
      );
    }
    if (row.stands) {
      const icn = row.dim ? `${DIM_ICON[row.dim]} ` : "";
      tags.push(el("span", { class: "tag stands", textContent: `${icn}${row.stands}` }));
    }
    const label = row.saved
      ? el(
          "span",
          { class: "lab" },
          lead,
          bookmark(),
          renaming === row.id
            ? nameInput(row)
            : el("span", { class: "vname", textContent: row.saved.name }),
          row.saved.kind === "manual"
            ? ""
            : el("span", { class: "kind", textContent: row.saved.kindLabel }),
          ...tags,
          el("span", { class: "sub", textContent: row.label }),
        )
      : el(
          "span",
          { class: "lab" },
          row.run
            ? el("span", {
                class: "chev",
                textContent: row.run.expanded ? "▾" : "▸",
                "aria-hidden": "true",
              })
            : "",
          lead,
          el("span", { class: "txt", textContent: row.label }),
          ...tags,
        );
    const node = el(
      "li",
      {
        class: classes.join(" "),
        role: "option",
        id: `hist-${row.id}`,
        tabIndex: selected ? 0 : -1,
        title: tip,
        "aria-selected": String(selected),
        dataset: { id: row.id },
      },
      label,
      el("span", { class: "t", textContent: row.head ? t("ui.history.now") : row.time }),
    );
    if (row.head) node.setAttribute("aria-current", "true");
    const description = [
      row.dimText || row.stands,
      row.restorePoint ? t("ui.history.restore_point") : "",
    ]
      .filter(Boolean)
      .join(", ");
    if (description) node.setAttribute("aria-description", description);
    if (row.run) node.setAttribute("aria-expanded", String(row.run.expanded));
    node.addEventListener("click", () => {
      pick(row.id);
      node.focus();
    });
    node.addEventListener("dblclick", () => {
      pick(row.id);
      if (row.id !== getState().historyCurrent) actions.restore(row.id);
    });
    return node;
  }

  /** The margin bracket from each restore row (in the current state) to its target. */
  function drawBrackets() {
    const marks = [];
    for (const row of rows) {
      if (row.kind !== "step" || !row.restoreTarget) continue;
      const from = rowOf(row.id);
      const to = rowOf(row.restoreTarget);
      if (!from || !to) continue;
      const top = from.offsetTop + from.offsetHeight / 2;
      const bottom = to.offsetTop + to.offsetHeight / 2;
      if (!Number.isFinite(top) || !Number.isFinite(bottom)) continue;
      const mark = el("div", {
        class: "hist-bracket",
        dataset: { from: row.id, to: row.restoreTarget },
      });
      mark.style.top = `${top}px`;
      mark.style.height = `${Math.max(0, bottom - top)}px`;
      marks.push(mark);
    }
    brackets.replaceChildren(...marks);
  }

  function draw() {
    const state = getState();
    const selected = state.historySelected;
    const next = JSON.stringify([
      getLanguage(),
      nodes,
      more,
      loading,
      selected,
      state.historyCurrent,
      state.canUndo,
      state.canRedo,
      savedOnly,
      query,
      renaming,
      expanded,
    ]);
    if (next === signature) return;
    signature = next;
    const keepFocus = list.contains(document.activeElement)
      ? document.activeElement.dataset.id
      : null;
    title.textContent = t("ui.history.title");
    list.setAttribute("aria-label", t("ui.history.list_label"));
    const shown = visibleNodes(nodes, { query, savedOnly });
    status.hidden = !(shown.length === 0 || loading);
    status.textContent = loading ? t("ui.history.loading") : t(emptyKey({ savedOnly, query }));
    filterGroup.setAttribute("aria-label", t("ui.history.filter_label"));
    showAll.textContent = t("ui.history.filter_all");
    showSaved.textContent = t("ui.history.filter_saved");
    showAll.setAttribute("aria-pressed", String(!savedOnly));
    showSaved.setAttribute("aria-pressed", String(savedOnly));
    savedHint.hidden = !savedOnly;
    savedHintText.textContent = t("ui.history.saved_hint");
    savedHintLink.textContent = t("ui.history.saved_hint_link");
    search.setAttribute("aria-label", t("ui.history.search_label"));
    search.placeholder = t("ui.history.search_placeholder");
    bar.setAttribute("aria-label", t("ui.history.undo_group"));
    undo.textContent = t("ui.transport.undo");
    redo.textContent = t("ui.transport.redo");
    undo.disabled = !state.canUndo;
    redo.disabled = !state.canRedo;
    older.hidden = !more || loading;
    older.textContent = t("ui.history.older");
    restore.textContent = t("ui.history.restore");
    restore.disabled =
      !selected || selected === state.historyCurrent || !nodes.some((n) => n.id === selected);
    hint.textContent = t("ui.history.restore_hint");
    rows = historyRows(shown, now(), t, { expanded, savedOnly, query });
    rowEls.clear();
    list.replaceChildren(
      ...rows.map((row) => {
        let node;
        if (row.kind === "marker") {
          node = el("li", {
            class: row.parent ? "hist-marker child" : "hist-marker",
            role: "separator",
            textContent: row.text,
          });
        } else if (row.kind === "group") {
          node = groupRow(row, row.id === selected);
        } else {
          node = stepRow(row, row.id === selected);
        }
        if (row.kind !== "marker") rowEls.set(row.id, node);
        return node;
      }),
    );
    drawBrackets();
    if (keepFocus) rowOf(keepFocus)?.focus({ preventScroll: true });
  }

  undo.addEventListener("click", () => actions.undo());
  redo.addEventListener("click", () => actions.redo());
  restore.addEventListener("click", () => {
    const { historySelected, historyCurrent } = getState();
    if (historySelected && historySelected !== historyCurrent) actions.restore(historySelected);
  });

  /** Right opens the picked group or run, Left closes it (or the one the pick is inside). */
  function openClose(open) {
    const id = getState().historySelected;
    const row = rows.find((r) => r.id === id);
    if (!row) return false;
    if (row.kind === "group") {
      if (row.expanded === open) return false;
      setOpen(row.id, open);
      return true;
    }
    if (row.run && row.run.expanded !== open) {
      setOpen(row.run.key, open);
      return true;
    }
    if (!open && row.parent) {
      setOpen(row.parent, false);
      // A run's id is "r:" and its first step's id; a group's row has the group's own id.
      focusRow(row.parent.startsWith("r:") ? row.parent.slice(2) : row.parent);
      return true;
    }
    return false;
  }

  root.addEventListener("keydown", (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (event.target.closest?.(".actionbar, .hist-filter, .hist-search, .hist-rename")) return;
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      if (openClose(event.key === "ArrowRight")) event.preventDefault();
      return;
    }
    if (event.key === "Enter") {
      // Enter on a group row opens or closes it; on a step the Restore command takes it.
      const row = rows.find((r) => r.id === getState().historySelected);
      if (row?.kind !== "group") return;
      event.preventDefault();
      event.stopPropagation();
      setOpen(row.id, !row.expanded);
      rowOf(row.id)?.focus();
      return;
    }
    const direction = { ArrowDown: 1, ArrowUp: -1 }[event.key];
    if (!direction) return;
    event.preventDefault();
    const next = moveRow(rows, getState().historySelected, direction);
    if (next) focusRow(next);
  });
  // The panel itself takes the keyboard (focus cycling): hand it to the picked step.
  root.addEventListener("focus", (event) => {
    if (event.target !== root) return;
    const id = getState().historySelected;
    (id && rowOf(id))?.focus();
  });

  /** Called on every state change: loads when shown, reloads when the head moved. */
  function update(state) {
    const shown = state.sidebarTab === "history" && !root.hidden && state.head;
    if (shown && loadedHead !== state.head && requestedHead !== state.head) {
      requestedHead = state.head;
      void reload(state.head);
    }
    draw();
    queueMicrotask(fillIfShort);
  }
  // Step names come from the server in the language of the request: ask again.
  onLanguageChange(() => {
    const head = getState().head;
    if (head && loadedLanguage !== undefined && loadedLanguage !== getLanguage()) {
      requestedHead = head;
      void reload(head);
    }
  });

  /** Rename the picked saved version in place; false when the pick is not one. */
  function startRename() {
    const picked = nodes.find((node) => node.id === getState().historySelected);
    if (!picked?.checkpoint) return false;
    renaming = picked.id;
    signature = "";
    draw();
    return true;
  }

  /** From a restore step, pick the step it restored: older pages are fetched and closed
   * groups opened until it is on screen. False when the pick is not a restore. */
  async function goToRestorePoint() {
    const target = restorePointOf(nodes, getState().historySelected);
    if (!target) return false;
    while (!nodes.some((node) => node.id === target) && more) {
      const before = nodes.length;
      await loadMore();
      if (nodes.length === before) break;
    }
    if (!nodes.some((node) => node.id === target)) return false;
    for (let pass = 0; pass < 3 && !rows.some((row) => row.id === target); pass++) {
      for (const row of rows) {
        if (row.members?.includes(target)) {
          expanded = { ...expanded, [row.kind === "group" ? row.id : row.run.key]: true };
        }
      }
      signature = "";
      draw();
    }
    focusRow(target);
    return true;
  }

  /** Open every group and run; when all are open, put them back as they were by default. */
  function expandAll() {
    expanded = expandAllMap(visibleNodes(nodes, { query, savedOnly }), now(), t, expanded);
    signature = "";
    draw();
  }

  return {
    update,
    startRename,
    goToRestorePoint,
    expandAll,
    toggleSavedOnly: () => setSavedOnly(!savedOnly),
    /** File > Open earlier version... and Go to > Open History at the saved versions. */
    showSavedVersions: () => setSavedOnly(true),
  };
}
