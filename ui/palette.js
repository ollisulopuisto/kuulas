// The command palette (Mod+K): a command bar docked over the sidebar column, no
// scrim, the timeline stays live (GUI-DESIGN 3.9). Rows are pure data (tested);
// the DOM part below only draws them.

import { matchCommand } from "./command-search.js";
import { fuzzyMatch } from "./fuzzy.js";

/**
 * Every command that matches `query`, with the user's current keys.
 * Enabled commands first, then ones that cannot apply right now, then planned ones.
 * -> [{ id, label, keys, planned, enabled, indices }]
 */
export function paletteRows({
  entries,
  registry,
  state,
  query = "",
  label,
  format,
  platform,
  recent = [],
  otherLabels = [],
  synonymsFor = () => [],
}) {
  const rows = [];
  // "Recent" first when the query is empty (GUI-DESIGN 3.9): commands that still exist
  // and can apply now, in the order they were last used.
  const recentRank = new Map();
  if (query.trim() === "") {
    for (const id of recent) {
      if (!recentRank.has(id) && registry.has(id) && registry.can(id, state)) {
        recentRank.set(id, recentRank.size);
      }
    }
  }
  entries.forEach((entry, order) => {
    const text = label(entry.labelKey);
    // The same matching as Help search (command-search.js): name in either language, every word
    // of the query, a word of the hint, a synonym. Letters in order (the palette's old habit)
    // still find a command, below all of those.
    const hintKey = registry.hintKey?.(entry.id);
    const hints = [hintKey, ...otherLabels.map(() => hintKey)]
      .map((key, i) => (key ? (i === 0 ? label(key) : otherLabels[i - 1](key)) : ""))
      .filter((hint) => hint && hint !== hintKey);
    const names = [text, ...otherLabels.map((other) => other(entry.labelKey))].filter(
      (name, i) => name && (i === 0 || name !== entry.labelKey),
    );
    const found = matchCommand({ names, hints, synonyms: synonymsFor(entry.id) }, query.trim());
    const fuzzy = fuzzyMatch(query.trim(), text);
    if (!found && !fuzzy) return;
    // Letters are lit only where the typed text is in the name itself.
    const nameHit = found ? found.tier >= 50 : true;
    const match = {
      indices: nameHit && fuzzy ? fuzzy.indices : [],
      score: found ? found.score : fuzzy.score - 100000,
    };
    const planned = registry.status(entry.id) !== "ready";
    const enabled = !planned && registry.can(entry.id, state);
    rows.push({
      id: entry.id,
      label: text,
      keys: entry.raw.map((raw) => format(raw, platform)),
      planned,
      enabled,
      indices: match.indices,
      score: match.score,
      group: planned ? 2 : enabled ? 0 : 1,
      order,
      recent: recentRank.has(entry.id) || undefined,
      rank: recentRank.get(entry.id),
    });
  });
  rows.sort(
    (a, b) =>
      (a.rank ?? Number.POSITIVE_INFINITY) - (b.rank ?? Number.POSITIVE_INFINITY) ||
      a.group - b.group ||
      b.score - a.score ||
      a.order - b.order,
  );
  return rows.map(({ score, group, order, rank, ...row }) => row);
}

/** Arrow keys: move and wrap; -1 when there is nothing to select. */
export function moveSelection(index, direction, count) {
  if (count <= 0) return -1;
  return (index + direction + count) % count;
}

/**
 * The docked bar. `getRows(query)` returns paletteRows; `run(id)` runs a command and
 * returns false when it could not (planned, cannot apply). Focus returns where it was.
 */
export function createPalette({ getRows, run, t, root = document.body }) {
  const panel = document.createElement("div");
  panel.className = "palette";
  panel.hidden = true;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", t("ui.palette.title"));
  const input = document.createElement("input");
  input.type = "text";
  input.className = "palette-input";
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-expanded", "true");
  input.setAttribute("aria-controls", "palette-list");
  input.setAttribute("aria-autocomplete", "list");
  input.autocomplete = "off";
  input.spellcheck = false;
  const list = document.createElement("ul");
  list.id = "palette-list";
  list.className = "palette-list";
  list.setAttribute("role", "listbox");
  const note = document.createElement("p");
  note.className = "palette-note hint";
  note.setAttribute("role", "status");
  panel.append(input, list, note);
  root.append(panel);

  let rows = [];
  let selected = 0;
  let returnTo = null;

  function draw() {
    rows = getRows(input.value);
    selected = Math.min(selected, Math.max(0, rows.length - 1));
    list.replaceChildren();
    // The "Recent" heading; the rest follows under none (the first recent row comes first).
    if (rows[0]?.recent) {
      const heading = document.createElement("li");
      heading.setAttribute("role", "presentation");
      heading.className = "palette-group";
      heading.textContent = t("ui.palette.recent");
      list.append(heading);
    }
    rows.forEach((row, index) => {
      const li = document.createElement("li");
      li.id = `palette-row-${index}`;
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", String(index === selected));
      if (!row.enabled) li.setAttribute("aria-disabled", "true");
      li.className = "palette-row";
      const name = document.createElement("span");
      name.className = "palette-name";
      const marked = new Set(row.indices);
      [...row.label].forEach((char, i) => {
        if (marked.has(i)) {
          const u = document.createElement("u");
          u.textContent = char;
          name.append(u);
        } else name.append(char);
      });
      if (row.planned) {
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = t("ui.keys.planned");
        name.append(" ", tag);
      }
      li.append(name);
      for (const key of row.keys.slice(0, 2)) {
        const kbd = document.createElement("kbd");
        kbd.textContent = key;
        li.append(kbd);
      }
      li.addEventListener("pointerdown", (event) => {
        event.preventDefault(); // keep focus in the field
        selected = index;
        accept();
      });
      list.append(li);
    });
    input.setAttribute("aria-activedescendant", rows.length ? `palette-row-${selected}` : "");
    if (rows.length === 0) note.textContent = t("ui.palette.none");
    else note.textContent = "";
    list.querySelector(`#palette-row-${selected}`)?.scrollIntoView?.({ block: "nearest" });
  }

  function accept() {
    const row = rows[selected];
    if (!row) return;
    if (run(row.id) === false) {
      note.textContent = t(row.planned ? "ui.palette.planned" : "ui.palette.unavailable");
      return;
    }
    close();
  }

  function open() {
    returnTo = document.activeElement;
    panel.hidden = false;
    input.value = "";
    selected = 0;
    draw();
    input.focus();
  }

  function close() {
    if (panel.hidden) return;
    panel.hidden = true;
    if (returnTo?.isConnected) returnTo.focus();
    returnTo = null;
  }

  input.addEventListener("input", () => {
    selected = 0;
    draw();
  });
  input.addEventListener("keydown", (event) => {
    const take = () => {
      event.preventDefault();
      event.stopPropagation();
    };
    if (event.key === "Escape") {
      take();
      close();
    } else if (event.key === "Enter") {
      take();
      accept();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      take();
      selected = moveSelection(selected, event.key === "ArrowDown" ? 1 : -1, rows.length);
      draw();
    }
  });

  return {
    element: panel,
    isOpen: () => !panel.hidden,
    open,
    close,
    toggle: () => (panel.hidden ? open() : close()),
    refresh: () => !panel.hidden && draw(),
  };
}
