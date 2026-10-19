// WP75: the Help search box. One widget, two places: the first item of the in-window Help menu
// (menubar.js embeds `element`), and a small panel over the window for the desktop app's native
// Help menu, which cannot hold a text field (createSearchPanel below). What a query finds and in
// which order is command-search.js; this file only draws it and takes the keys.
//
// Keys inside the field: Up/Down move through the results, Enter runs the command (or opens the
// help topic), Alt+Enter shows the command in its menu, Esc closes. Letters are the field's own:
// nothing here or in the menu bar treats them as mnemonics, and the keymap ignores plain keys
// while a text field has focus (keys.js isTextField).

import { moveSelection } from "./palette.js";

let serial = 0;

/**
 * search(query) -> { commands, topics, recent } (command-search.js searchAll);
 * run(id) runs a command, returns false when it could not; reveal(id) opens the item's menu and
 * highlights it, returns false when the command is in no menu; openTopic(id) opens a help topic.
 * hooks (settable later, setHooks): close({ restoreFocus }) leaves the search; exit(key) when an
 * arrow key has nothing to do in the field (the menu bar moves on); onOpenTopics() to load topics.
 */
export function createCommandSearch({ t, search, run, reveal, openTopic, hooks = {} }) {
  const id = `cmd-search-${++serial}`;
  const root = document.createElement("div");
  root.className = "cmd-search";

  const input = document.createElement("input");
  input.type = "text";
  input.className = "cmd-search-input";
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", `${id}-list`);
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-keyshortcuts", "Alt+Enter");
  input.autocomplete = "off";
  input.spellcheck = false;
  input.enterKeyHint = "go";

  const list = document.createElement("ul");
  list.id = `${id}-list`;
  list.className = "cmd-search-list";
  list.setAttribute("role", "listbox");

  const note = document.createElement("p");
  note.className = "cmd-search-note hint";

  // Announces how many results there are; the visible note only carries messages.
  const live = document.createElement("span");
  live.className = "visually-hidden";
  live.setAttribute("role", "status");
  live.setAttribute("aria-live", "polite");

  root.append(input, list, note, live);

  const label = document.createElement("label");
  label.className = "visually-hidden";
  label.htmlFor = `${id}-input`;
  input.id = `${id}-input`;
  root.prepend(label);

  let rows = []; // the options in order: commands, then topics
  let selected = 0;
  let current = { commands: [], topics: [], recent: false };
  const callHooks = () => hooks;

  function chrome() {
    input.placeholder = t("ui.search.placeholder");
    input.setAttribute("aria-label", t("ui.search.label"));
    label.textContent = t("ui.search.label");
    list.setAttribute("aria-label", t("ui.search.results"));
  }

  function heading(text) {
    const li = document.createElement("li");
    li.setAttribute("role", "presentation");
    li.className = "cmd-search-group";
    li.textContent = text;
    return li;
  }

  function commandRow(row, index) {
    const li = document.createElement("li");
    li.id = `${id}-row-${index}`;
    li.setAttribute("role", "option");
    li.className = "cmd-search-row";
    if (!row.enabled) li.setAttribute("aria-disabled", "true");

    const head = document.createElement("div");
    head.className = "cmd-search-head";
    const name = document.createElement("span");
    name.className = "cmd-search-name";
    name.textContent = row.name;
    head.append(name);
    if (row.keys.length > 0) {
      const kbd = document.createElement("kbd");
      kbd.textContent = row.keys[0];
      head.append(kbd);
    } else {
      const none = document.createElement("span");
      none.className = "cmd-search-nokey";
      none.textContent = t("ui.search.no_key");
      head.append(none);
    }
    li.append(head);

    const where = document.createElement("div");
    where.className = "cmd-search-where";
    where.textContent = row.where ?? t("ui.search.palette_only");
    li.append(where);

    if (row.hint) {
      const hint = document.createElement("div");
      hint.className = "cmd-search-hint";
      hint.textContent = row.hint;
      li.append(hint);
    }
    if (!row.enabled && row.reason) {
      const why = document.createElement("div");
      why.className = "cmd-search-reason";
      why.textContent = row.reason;
      li.append(why);
    }
    if (!row.paletteOnly) {
      // For the pointer; the keyboard has Alt+Enter, announced on the field (aria-keyshortcuts).
      const show = document.createElement("button");
      show.type = "button";
      show.tabIndex = -1;
      show.className = "cmd-search-show";
      show.setAttribute("aria-hidden", "true");
      show.textContent = t("ui.search.show_in_menu");
      show.addEventListener("pointerdown", (event) => {
        event.preventDefault(); // keep focus in the field
        event.stopPropagation();
        selected = index;
        showInMenu();
      });
      li.append(show);
    }
    return li;
  }

  function topicRow(row, index) {
    const li = document.createElement("li");
    li.id = `${id}-row-${index}`;
    li.setAttribute("role", "option");
    li.className = "cmd-search-row cmd-search-topic";
    const name = document.createElement("span");
    name.className = "cmd-search-name";
    name.textContent = row.title;
    li.append(name);
    if (row.gist) {
      const gist = document.createElement("div");
      gist.className = "cmd-search-hint";
      gist.textContent = row.gist;
      li.append(gist);
    }
    return li;
  }

  function draw() {
    chrome();
    const query = input.value.trim();
    current = search(input.value);
    rows = [
      ...current.commands.map((row) => ({ kind: "command", row })),
      ...current.topics.map((row) => ({ kind: "topic", row })),
    ];
    selected = Math.min(selected, Math.max(0, rows.length - 1));
    list.replaceChildren();
    if (current.commands.length > 0) {
      list.append(heading(t(current.recent ? "ui.search.recent" : "ui.search.commands")));
    }
    rows.forEach((entry, index) => {
      if (index === current.commands.length && current.topics.length > 0) {
        list.append(heading(t("ui.search.topics")));
      }
      const li =
        entry.kind === "command" ? commandRow(entry.row, index) : topicRow(entry.row, index);
      li.setAttribute("aria-selected", String(index === selected));
      li.addEventListener("pointerdown", (event) => {
        event.preventDefault(); // keep focus in the field
        selected = index;
        accept({ alt: false });
      });
      list.append(li);
    });
    const open = rows.length > 0;
    input.setAttribute("aria-expanded", String(open));
    if (open) input.setAttribute("aria-activedescendant", `${id}-row-${selected}`);
    else input.removeAttribute("aria-activedescendant");
    list.hidden = !open;
    if (open) note.textContent = t("ui.search.footer");
    else note.textContent = query ? t("ui.search.none", { query }) : t("ui.search.empty");
    live.textContent = open && query ? t("ui.search.found", { count: rows.length }) : "";
    list.querySelector(`#${id}-row-${selected}`)?.scrollIntoView?.({ block: "nearest" });
  }

  function select(index) {
    selected = index;
    for (const [i, li] of [...list.querySelectorAll('[role="option"]')].entries()) {
      li.setAttribute("aria-selected", String(i === selected));
    }
    input.setAttribute("aria-activedescendant", `${id}-row-${selected}`);
    list.querySelector(`#${id}-row-${selected}`)?.scrollIntoView?.({ block: "nearest" });
  }

  function showInMenu() {
    const entry = rows[selected];
    if (entry?.kind !== "command") return;
    if (entry.row.paletteOnly) {
      note.textContent = t("ui.search.not_in_menu");
      return;
    }
    if (reveal(entry.row.id) === false) note.textContent = t("ui.search.not_in_menu");
    else callHooks().revealed?.();
  }

  function accept({ alt }) {
    const entry = rows[selected];
    if (!entry) return;
    if (entry.kind === "topic") {
      callHooks().close?.({ restoreFocus: false });
      openTopic(entry.row.id);
      return;
    }
    if (alt) return showInMenu();
    if (!entry.row.enabled) {
      // Greyed: it stays in the list and says why (no project open, not built yet).
      note.textContent = entry.row.reason ?? t("ui.search.reason.unavailable");
      return;
    }
    callHooks().close?.({ restoreFocus: false });
    run(entry.row.id);
  }

  input.addEventListener("input", () => {
    selected = 0;
    draw();
  });
  input.addEventListener("keydown", (event) => {
    if (event.isComposing) return;
    const take = () => {
      event.preventDefault();
      event.stopPropagation();
    };
    if (event.key === "Escape") {
      take();
      callHooks().close?.({ restoreFocus: true });
    } else if (event.key === "Enter") {
      take();
      accept({ alt: event.altKey });
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      take();
      if (rows.length === 0) callHooks().exit?.(event.key);
      else select(moveSelection(selected, event.key === "ArrowDown" ? 1 : -1, rows.length));
    } else if ((event.key === "ArrowLeft" || event.key === "ArrowRight") && !input.value) {
      // An empty field has no caret to move: the arrows go on to the menu bar.
      take();
      callHooks().exit?.(event.key);
    } else if (event.key === "Tab") {
      callHooks().close?.({ restoreFocus: false });
    }
  });
  // Not drawn yet: the first search happens when the field is opened (reset), by which time
  // everything it reads (help topics, the registry) exists.
  chrome();

  return {
    element: root,
    input,
    setHooks: (next) => Object.assign(hooks, next),
    focus() {
      input.focus();
    },
    isFocused: () => root.contains(root.ownerDocument.activeElement),
    /** Forget the query (the menu closed). */
    reset() {
      input.value = "";
      selected = 0;
      draw();
    },
    /** Search again: the language, the keys, the state or the loaded help topics changed. */
    refresh: draw,
  };
}

/**
 * The same search as a small panel over the window (the desktop app's native Help menu item
 * "Search commands…"). `makeSearch(hooks)` builds a createCommandSearch with its hooks; reveal
 * is not available there (the in-window bar may be hidden), so the panel runs and opens topics.
 */
export function createSearchPanel({ t, makeSearch, root = document.body }) {
  const panel = document.createElement("div");
  panel.className = "cmd-search-panel";
  panel.hidden = true;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", t("ui.search.panel"));
  let returnTo = null;

  const close = ({ restoreFocus = true } = {}) => {
    if (panel.hidden) return;
    panel.hidden = true;
    search.reset();
    if (restoreFocus && returnTo?.isConnected) returnTo.focus();
    returnTo = null;
  };
  const search = makeSearch({
    close,
    revealed: () => close({ restoreFocus: false }),
    exit: () => {}, // nothing to move on to: the arrows stay in the field
  });
  panel.append(search.element);
  root.append(panel);
  // Focus leaving for somewhere else (a click on the page) closes it, as a menu does.
  panel.addEventListener("focusout", (event) => {
    if (!panel.hidden && event.relatedTarget && !panel.contains(event.relatedTarget)) {
      close({ restoreFocus: false });
    }
  });
  document.addEventListener("pointerdown", (event) => {
    if (!panel.hidden && !panel.contains(event.target)) close({ restoreFocus: false });
  });

  return {
    element: panel,
    isOpen: () => !panel.hidden,
    open() {
      if (panel.hidden) returnTo = document.activeElement;
      panel.setAttribute("aria-label", t("ui.search.panel"));
      panel.hidden = false;
      search.refresh();
      search.focus();
    },
    close,
    refresh: () => !panel.hidden && search.refresh(),
  };
}
