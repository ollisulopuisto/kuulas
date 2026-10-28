// The side panel (Inspector, Candidates, Clipboard, Markers, History, and the docked Help and
// Auto-Silence panels) can be hidden so the timeline gets the width (owner, 2026-10-21). The
// pure part: the remembered value, the switch, and which commands need the panel and so show it
// again. app.js applies it (state `sidebarShown`, the `data-sidebar` attribute on the editor).

/** The remembered-preference key (ui/prefs.js). */
export const SIDEBAR_KEY = "sidebar";

/** Shown unless the remembered value says hidden (so a missing or odd value shows it). */
export const sidebarShown = (pref) => pref !== "hidden";

/** The value to remember. */
export const sidebarPref = (shown) => (shown ? "shown" : "hidden");

export const toggleSidebar = (shown) => !shown;

/** Commands that put something in the sidebar or move the focus there. */
const NEEDS_SIDEBAR = new Set([
  "help.open",
  "app.auto_silence_options",
  "panel.next",
  "panel.previous",
  "panel.show_inspector",
  "panel.show_candidates",
  "panel.show_clipboard",
  "panel.show_material",
  "panel.show_markers",
  "panel.show_history",
]);

export const opensSidebar = (id) => NEEDS_SIDEBAR.has(id);

/** Whether the sidebar shows after command `id` runs. */
export const sidebarAfter = (shown, id) => shown || opensSidebar(id);
