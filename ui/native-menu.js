// The macOS menu bar copy of the in-window menu (docs/desktop.md, "The native menu bar").
// The window's menu stays the one real menu: this file turns the same resolved menu
// (menu-model.js `resolveMenu`) into plain data and hands it to the desktop wrapper, which
// draws it as native menus. A native item does nothing by itself: choosing it sends the
// command id (and `arg`) back to `window.__kuulasNativeRun`, which runs the same command
// as the in-window item. Keys are shown, never bound, so the keymap stays the one owner of keys.

/** Longest menu the wrapper accepts; the real menu is a few hundred items. */
export const MAX_NATIVE_ITEMS = 800;

/**
 * Resolved menus -> the data the wrapper draws: `[{ label, items }]` where an item is
 * `{ kind: "item", id, arg?, label, keys, enabled, checked? }`, `{ kind: "separator" }` or
 * `{ kind: "submenu", label, items }`. The Help search field is left out (it is a text box),
 * separators never lead, trail or repeat, and an empty submenu is dropped.
 */
export function nativeMenuSpec(menus) {
  let budget = MAX_NATIVE_ITEMS;

  function clean(items) {
    const out = [];
    for (const entry of items ?? []) {
      if (budget <= 0) break;
      if (entry.kind === "separator") {
        if (out.length > 0 && out[out.length - 1].kind !== "separator")
          out.push({ kind: "separator" });
        continue;
      }
      if (entry.kind === "search") continue;
      budget -= 1;
      if (entry.kind === "submenu") {
        const inner = clean(entry.items);
        if (inner.length > 0)
          out.push({ kind: "submenu", label: String(entry.label ?? ""), items: inner });
        continue;
      }
      const item = {
        kind: "item",
        id: String(entry.id),
        label: String(entry.label ?? ""),
        keys: String(entry.keys ?? ""),
        enabled: Boolean(entry.enabled),
      };
      if (entry.arg !== undefined && entry.arg !== null) item.arg = String(entry.arg);
      if (typeof entry.checked === "boolean") item.checked = entry.checked;
      out.push(item);
    }
    while (out.length > 0 && out[out.length - 1].kind === "separator") out.pop();
    return out;
  }

  return (menus ?? [])
    .map((menu) => ({
      id: String(menu.id ?? ""),
      label: String(menu.label ?? ""),
      items: clean(menu.items),
    }))
    .filter((menu) => menu.items.length > 0);
}

/**
 * Hides the in-window menu while the wrapper holds the same menu natively
 * (owner, 2026-11-19: "now that we have the native menu, we don't need to
 * duplicate it inside the app window"): marks the document root, and the CSS
 * drops the menu bar and slims the top bar to the brand and mode chips. A
 * plain browser has no wrapper API and keeps its menu. Returns whether the
 * window menu is hidden.
 */
export function syncWindowMenuHidden(doc, api) {
  const hidden = Boolean(api && typeof api.set_native_menu === "function");
  doc.documentElement.toggleAttribute("data-native-menu", hidden);
  return hidden;
}

/**
 * Keeps the native menus in step with the window: `push()` sends the menu when it changed
 * (after `delay` ms, so a burst of state changes is one send, but never later than `maxWait` ms). Only the window that has focus
 * sends, since the bar belongs to the front window; `push(true)` (on focus) sends at once, regardless of
 * the last spec. Does nothing without the wrapper's `set_native_menu`, so a browser tab is untouched.
 */
export function createNativeMenuSync({
  getMenus,
  getApi,
  hasFocus = () => true,
  delay = 150,
  maxWait = 500,
  now = Date.now,
  setTimer = setTimeout,
  clearTimer = clearTimeout,
}) {
  let last = "";
  let timer = null;
  let firstAt = 0;

  function send() {
    if (timer !== null) clearTimer(timer);
    timer = null;
    firstAt = 0;
    const api = getApi();
    if (!api || typeof api.set_native_menu !== "function" || !hasFocus()) return;
    const spec = nativeMenuSpec(getMenus());
    const text = JSON.stringify(spec);
    if (text === last) return;
    last = text;
    Promise.resolve(api.set_native_menu(spec)).catch(() => {
      last = ""; // let the next change try again
    });
  }

  return {
    push(force = false) {
      if (force) {
        // Taking the bar must not wait behind a stream of state changes (the playhead).
        last = "";
        send();
        return;
      }
      const t = now();
      if (timer === null) firstAt = t;
      else clearTimer(timer);
      // A steady stream still sends: at the latest `maxWait` ms after the first change.
      timer = setTimer(send, Math.max(0, Math.min(delay, firstAt + maxWait - t)));
    },
  };
}

/**
 * A chosen native item, run like its key: an editing command (`registry.explains`) is
 * refused while a modal dialog is open, so a native Cut or Undo cannot change the project
 * behind Preferences. Anything else (and the dialog's own controls, which are not menu
 * items) works as before. Returns true when the command ran.
 */
export function runNativeChoice(choice, { registry, getState, isModal }) {
  if (!choice || typeof choice.id !== "string") return false;
  if (isModal() && (registry.explains?.(choice.id) ?? false)) return false;
  registry.run(choice.id, choice.arg ?? null, getState());
  return true;
}

/** The menus with the editing items switched off while a modal dialog is open. */
export function isolateMenusForModal(menus, { explains, isModal }) {
  if (!isModal()) return menus;
  const walk = (items) =>
    (items ?? []).map((entry) => {
      if (entry?.kind === "item" && (explains?.(entry.id) ?? false))
        return { ...entry, enabled: false };
      return entry?.kind === "submenu" ? { ...entry, items: walk(entry.items) } : entry;
    });
  return (menus ?? []).map((menu) => ({ ...menu, items: walk(menu.items) }));
}
