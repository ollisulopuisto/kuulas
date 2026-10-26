// What the toolbar remembers per user (WP86): the layout, icons with or without text, and whether
// it is shown. `prefs` is the app's guarded store (prefs.js), so a blocked storage only means
// "not remembered".
import { normalizeLayout } from "./toolbar-model.js";

const LAYOUT_KEY = "toolbar.layout";
const MODE_KEY = "toolbar.mode";
const VISIBLE_KEY = "toolbar.visible";

/** "labels" = icon and text, "icons" = icon only. Text is the default: it is what helps discovery. */
export const MODES = ["labels", "icons"];
export const DEFAULT_MODE = "labels";

/** The mode View > "Show text on toolbar buttons" switches to; anything unknown counts as the default. */
export const otherMode = (mode) => (mode === "icons" ? "labels" : "icons");

export const readLayout = (prefs, known) => normalizeLayout(prefs.getJson(LAYOUT_KEY, null), known);

export const writeLayout = (prefs, layout) => prefs.setJson(LAYOUT_KEY, layout);

export function readMode(prefs) {
  const stored = prefs.get(MODE_KEY);
  return MODES.includes(stored) ? stored : DEFAULT_MODE;
}

export const writeMode = (prefs, mode) =>
  MODES.includes(mode) ? prefs.set(MODE_KEY, mode) : false;

export const readVisible = (prefs) => prefs.get(VISIBLE_KEY) !== "false";

export const writeVisible = (prefs, visible) => prefs.set(VISIBLE_KEY, visible ? "true" : "false");
