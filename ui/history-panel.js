// The History tab (WP8): the steps of the edit, newest first, in pages as you scroll.
// Session markers are thin dividers, the current step is highlighted, steps on the redo
// side are dimmed, and steps left on an abandoned branch are dimmed and indented. A click
// picks a step; Restore (Enter) adds a new step equal to it and loses nothing. The logic
// is history-model.js's; what Restore does is app.js's (actions.restore).

import {
  currentStep,
  groupRows,
  mergePage,
  moveSelection,
  needsMore,
  selectionAfterLoad,
} from "./history-model.js";
import { formatAbsoluteTime, getLanguage, t } from "./i18n.js";

const PAGE = 100;
const PAGE_MAX = 500; // the server's limit per request

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

/**
 * `api.getHistory({ limit, before })` answers { nodes, more }; `actions.restore(id)`,
 * `actions.undo()`, `actions.redo()`, `actions.showError(error)`. `now()` is the clock (tests and the page differ).
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
  let token = 0;
  let signature = "";

  const list = el("ul", {
    class: "hist",
    role: "listbox",
    "aria-label": t("ui.history.list_label"),
  });
  const scroller = el("div", { class: "hist-scroll" }, list);
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
  root.replaceChildren(title, bar, status, scroller, older);

  async function fetchPage(before, limit) {
    const page = await api.getHistory({ limit, before });
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

  function pick(id) {
    if (getState().historySelected !== id) setState({ historySelected: id });
  }

  const rowOf = (id) => list.querySelector(`[data-id="${CSS.escape(id)}"]`);

  function stepRow(row, selected) {
    const classes = ["hist-step"];
    if (row.head) classes.push("head");
    if (row.dimmed) classes.push("future");
    if (row.redo) classes.push("redo");
    if (row.indent) classes.push("branch");
    const stateText = row.head
      ? t("ui.history.head_title")
      : row.redo
        ? t("ui.history.redo_title")
        : row.indent
          ? t("ui.history.branch_title")
          : "";
    const tip = [formatAbsoluteTime(row.created), stateText].filter(Boolean).join(" · ");
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
      el("span", { class: "lab", textContent: row.label }),
      el("span", { class: "t", textContent: row.head ? t("ui.history.now") : row.time }),
    );
    if (row.head) node.setAttribute("aria-current", "true");
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
    ]);
    if (next === signature) return;
    signature = next;
    const keepFocus = list.contains(document.activeElement)
      ? document.activeElement.dataset.id
      : null;
    title.textContent = t("ui.history.title");
    list.setAttribute("aria-label", t("ui.history.list_label"));
    status.hidden = !(nodes.length === 0 || loading);
    status.textContent = loading ? t("ui.history.loading") : t("ui.history.empty");
    bar.setAttribute("aria-label", t("ui.history.undo_group"));
    undo.textContent = t("ui.transport.undo");
    redo.textContent = t("ui.transport.redo");
    undo.disabled = !state.canUndo;
    redo.disabled = !state.canRedo;
    older.hidden = !more || loading;
    older.textContent = t("ui.history.older");
    restore.textContent = t("ui.history.restore");
    restore.disabled = !selected || selected === state.historyCurrent;
    hint.textContent = t("ui.history.restore_hint");
    list.replaceChildren(
      ...groupRows(nodes, now(), t).map((row) =>
        row.kind === "marker"
          ? el("li", { class: "hist-marker", role: "separator", textContent: row.text })
          : stepRow(row, row.id === selected),
      ),
    );
    if (keepFocus) rowOf(keepFocus)?.focus({ preventScroll: true });
  }

  undo.addEventListener("click", () => actions.undo());
  redo.addEventListener("click", () => actions.redo());
  restore.addEventListener("click", () => {
    const { historySelected, historyCurrent } = getState();
    if (historySelected && historySelected !== historyCurrent) actions.restore(historySelected);
  });

  root.addEventListener("keydown", (event) => {
    const direction = { ArrowDown: 1, ArrowUp: -1 }[event.key];
    if (!direction || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (event.target.closest?.(".actionbar")) return;
    event.preventDefault();
    const next = moveSelection(nodes, getState().historySelected, direction);
    if (!next) return;
    pick(next);
    draw();
    const row = rowOf(next);
    row?.focus();
    row?.scrollIntoView({ block: "nearest" });
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

  return { update };
}
