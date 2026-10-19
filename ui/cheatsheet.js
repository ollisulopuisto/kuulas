// The keyboard sheet ("?"). Data first (pure, tested), then the dialog.
// Generated from the keymap the user actually has, grouped by context.

import { fuzzyMatch } from "./fuzzy.js";
import { CONTEXTS } from "./keymap-default.js";
import { modifierLayers } from "./modifiers.js";

export const contextTitleKey = (context) => `keys.context.${context}`;

/** [{ context, rows: [{ id, label, keys, planned, layers }] }], empty groups dropped. */
export function cheatSheetData({ entries, registry, query = "", label, format, platform }) {
  const layers = modifierLayers(entries, platform);
  const needle = query.trim().toLocaleLowerCase();
  const groups = [];
  for (const context of CONTEXTS) {
    const rows = [];
    for (const entry of entries.filter((e) => e.context === context)) {
      const row = {
        id: entry.id,
        label: label(entry.labelKey),
        keys: entry.raw.map((raw) => format(raw, platform)),
        planned: registry.status(entry.id) !== "ready",
        layers: (layers.get(entry.id) ?? []).map((layer) => ({
          modifier: layer.modifier,
          id: layer.entry.id,
          label: label(layer.entry.labelKey),
          keys: layer.entry.raw.map((raw) => format(raw, platform)),
        })),
      };
      if (needle) {
        const byKey = row.keys.join(" ").toLocaleLowerCase().includes(needle);
        if (!byKey && !fuzzyMatch(needle, row.label)) continue;
      }
      rows.push(row);
    }
    if (rows.length > 0) groups.push({ context, rows });
  }
  return groups;
}

/**
 * The dialog. `t` translates; `actions` = { importKeys, exportKeys, resetKeys }.
 * Rebuilt from live data on every open and on every keymap or modifier change.
 */
export function createCheatSheet({ getData, t, actions, getHeld }) {
  const dialog = document.createElement("dialog");
  dialog.className = "cheatsheet";
  dialog.setAttribute("aria-labelledby", "cheatsheet-title");
  const heading = document.createElement("h2");
  heading.id = "cheatsheet-title";
  const search = document.createElement("input");
  search.type = "search";
  search.className = "cheatsheet-search";
  const body = document.createElement("div");
  body.className = "cheatsheet-body";
  const footer = document.createElement("div");
  footer.className = "cheatsheet-footer";
  const buttons = [
    ["keymap.import", actions.importKeys],
    ["keymap.export", actions.exportKeys],
    ["keymap.reset", actions.resetKeys],
  ].map(([id, run]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button";
    button.dataset.id = id;
    button.dataset.icon = id.split(".")[1];
    button.addEventListener("click", () => run());
    return button;
  });
  const close = document.createElement("button");
  close.type = "button";
  close.className = "button primary";
  close.dataset.icon = "close";
  close.addEventListener("click", () => dialog.close());
  footer.append(...buttons, close);
  dialog.append(heading, search, body, footer);
  document.body.append(dialog);

  function render() {
    heading.textContent = t("ui.keys.title");
    search.placeholder = t("ui.keys.search");
    search.setAttribute("aria-label", t("ui.keys.search"));
    for (const button of buttons) button.textContent = t(`cmd.${button.dataset.id}`);
    close.textContent = t("ui.keys.close");
    body.replaceChildren();
    const groups = getData(search.value);
    if (groups.length === 0) {
      const none = document.createElement("p");
      none.className = "hint";
      none.textContent = t("ui.keys.none");
      body.append(none);
    }
    const held = getHeld?.() ?? {};
    for (const group of groups) {
      const section = document.createElement("section");
      const title = document.createElement("h3");
      title.textContent = t(contextTitleKey(group.context));
      const table = document.createElement("table");
      for (const row of group.rows) {
        table.append(rowElement(row, held));
      }
      section.append(title, table);
      body.append(section);
    }
  }

  function rowElement(row, held) {
    const tr = document.createElement("tr");
    if (row.planned) tr.className = "planned";
    const name = document.createElement("td");
    name.textContent = row.label;
    if (row.planned) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = ` ${t("ui.keys.planned")}`;
      name.append(tag);
    }
    const keys = document.createElement("td");
    keys.className = "keys";
    appendKeys(keys, row.keys);
    tr.append(name, keys);
    if (row.layers.length === 0) return tr;
    // The same key with Shift or Alt held: listed under the plain key, as the
    // menus show it while the modifier is down.
    const wrap = document.createDocumentFragment();
    wrap.append(tr);
    for (const layer of row.layers) {
      const sub = document.createElement("tr");
      sub.className = "layer";
      if (held[layer.modifier.split("+")[0]]) sub.dataset.held = "";
      const n = document.createElement("td");
      n.textContent = [t(`ui.keys.layer.${layer.modifier}`), layer.label].join(" ");
      const k = document.createElement("td");
      k.className = "keys";
      appendKeys(k, layer.keys);
      sub.append(n, k);
      wrap.append(sub);
    }
    return wrap;
  }

  function appendKeys(cell, keys) {
    for (const key of keys) {
      const kbd = document.createElement("kbd");
      kbd.textContent = key;
      cell.append(kbd, " ");
    }
  }

  search.addEventListener("input", render);
  return {
    element: dialog,
    isOpen: () => dialog.open,
    open() {
      search.value = "";
      render();
      if (!dialog.open) dialog.showModal();
      search.focus();
    },
    toggle() {
      if (dialog.open) dialog.close();
      else this.open();
    },
    refresh() {
      if (dialog.open) render();
    },
  };
}
