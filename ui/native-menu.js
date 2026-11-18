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
 * Keeps the native menus in step with the window: `push()` sends the menu when it changed
 * (after `delay` ms, so a burst of state changes is one send). Only the window that has focus
 * sends, since the bar belongs to the front window; `push(true)` (on focus) sends regardless of
 * the last spec. Does nothing without the wrapper's `set_native_menu`, so a browser tab is untouched.
 */
export function createNativeMenuSync({
  getMenus,
  getApi,
  hasFocus = () => true,
  delay = 150,
  setTimer = setTimeout,
  clearTimer = clearTimeout,
}) {
  let last = "";
  let timer = null;

  function send() {
    timer = null;
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
      if (force) last = "";
      if (timer !== null) clearTimer(timer);
      timer = setTimer(send, delay);
    },
  };
}
