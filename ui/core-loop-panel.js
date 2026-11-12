// The core-loop onboarding panel (core-loop-model.js): a card docked at the bottom of the
// timeline stack, kept open while the user edits. Each row shows the key the command has
// now (remaps show), and ticks when the command runs - app.js feeds it from the registry.
// A non-modal section, never a dialog: the loop is tried by editing, and a modal would be
// in the way of exactly that.

import { CORE_LOOP, TOTAL, triedCount } from "./core-loop-model.js";
import { keyName } from "./i18n.js";

// Apple's order (i18n.js MAC_ORDER): control, option, shift, command.
const MOD_ORDER = ["Ctrl", "Alt", "Shift", "Mod"];

/**
 * One chip per key: "Shift+Mod+Space" -> ["⇧", "⌘", "Space"] on a Mac, named
 * ["Shift", "Ctrl", "Space"] elsewhere. An unbound command is no chips, never an error.
 */
export function comboParts(combo, platform = "other") {
  const keys = String(combo ?? "")
    .split("+")
    .filter(Boolean);
  if (keys.length === 0) return [];
  const ordered =
    platform === "mac"
      ? [
          ...MOD_ORDER.filter((mod) => keys.includes(mod)),
          ...keys.filter((key) => !MOD_ORDER.includes(key)),
        ]
      : keys;
  return ordered.map((key) => keyName(key, platform));
}

/**
 * `root`: the <section id="core-loop"> from index.html. `keyOf(command)` is the command's
 * current combo or null; `undoCombo` fills the cut row's "{undo} brings it back".
 * `onHide()` persists the dismissal; the panel only hides itself.
 */
export function createCoreLoopPanel({ root, t, platform, keyOf, undoCombo, onHide }) {
  const rows = new Map();
  let progress = null;

  function kbdChip(label) {
    const chip = document.createElement("kbd");
    chip.textContent = label;
    return chip;
  }

  function buildRow(entry) {
    const row = document.createElement("div");
    row.className = "cl-row";
    row.dataset.row = entry.id;
    row.setAttribute("role", "listitem");

    const dot = document.createElement("span");
    dot.className = "cl-dot";
    dot.setAttribute("aria-hidden", "true");
    dot.textContent = "✓";

    const keys = document.createElement("div");
    keys.className = "cl-keys";
    for (const part of comboParts(keyOf(entry.command), platform)) keys.append(kbdChip(part));

    const text = document.createElement("div");
    const name = document.createElement("div");
    name.className = "cl-name";
    name.textContent = t(`ui.coreloop.row.${entry.id}`);
    const hint = document.createElement("div");
    hint.className = "cl-hint";
    hint.textContent = t(`ui.coreloop.row.${entry.id}.hint`, {
      undo: undoCombo ? comboParts(undoCombo, platform).join("") : "",
    });
    text.append(name, hint);

    row.append(dot, keys, text);
    return row;
  }

  function render() {
    rows.clear();
    root.replaceChildren();

    const header = document.createElement("header");
    header.className = "cl-header";
    const title = document.createElement("h2");
    title.className = "cl-title";
    title.textContent = t("ui.coreloop.title");
    progress = document.createElement("span");
    progress.className = "cl-progress";
    progress.setAttribute("aria-live", "polite");
    header.append(title, progress);

    const intro = document.createElement("p");
    intro.className = "cl-intro";
    intro.textContent = t("ui.coreloop.intro");

    const list = document.createElement("div");
    list.className = "cl-rows";
    list.setAttribute("role", "list");
    for (const entry of CORE_LOOP) {
      const row = buildRow(entry);
      rows.set(entry.id, row);
      list.append(row);
    }

    const footer = document.createElement("div");
    footer.className = "cl-footer";
    const note = document.createElement("span");
    note.textContent = t("ui.coreloop.footer");
    const hide = document.createElement("button");
    hide.type = "button";
    hide.className = "button ghost small";
    hide.textContent = t("ui.coreloop.hide");
    hide.addEventListener("click", () => {
      root.hidden = true;
      onHide?.();
    });
    footer.append(note, hide);

    root.append(header, intro, list, footer);
  }

  render();

  return {
    element: root,
    show() {
      render();
      root.hidden = false;
    },
    hide() {
      root.hidden = true;
    },
    /** Reflects the remembered state: done rows ticked, the counter current. */
    update(state) {
      for (const entry of CORE_LOOP)
        rows.get(entry.id)?.classList.toggle("done", state.tried.includes(entry.id));
      if (progress)
        progress.textContent = t("ui.coreloop.progress", {
          tried: triedCount(state),
          total: TOTAL,
        });
    },
    /** The row that just ticked flashes; the done class stays. */
    flash(id) {
      const row = rows.get(id);
      if (!row) return;
      row.classList.add("flash");
      setTimeout(() => row.classList.remove("flash"), 400);
    },
  };
}
