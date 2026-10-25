// Teaching where a command lives (owner, 2026-10-24: "that Mac thing where when you press a
// shortcut it flashes the menu"). macOS flashes the title of the menu that holds a command when
// its key equivalent runs; the page's own menu bar does the same. Only chords with Cmd, Ctrl or
// Alt do: Space, J K L and the arrows would make the bar flicker all the time.
import { findItem } from "./menu-model.js";

/** The index of the top-level menu to flash for `id` run by the key event, or null. */
export function flashTop(menus, id, event) {
  if (!(event?.metaKey || event?.ctrlKey || event?.altKey)) return null;
  return findItem(menus, id)?.top ?? null;
}
