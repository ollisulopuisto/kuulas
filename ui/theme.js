// Colours for the canvases come from the custom properties in tokens.css, so
// light and dark (and any later theme) are changed in one place. Token names
// and their roles: docs/design/GUI-DESIGN.md, "Visual language".
import { MUSIC_HUE, SPEAKER_HUES } from "./paint.js";

/** The user's theme choice. "system" follows the OS (prefers-color-scheme). */
export const THEMES = ["system", "light", "dark"];

export function nextTheme(current) {
  const at = THEMES.indexOf(current);
  return THEMES[(Math.max(0, at) + 1) % THEMES.length];
}

/** The value of <html data-theme>, or null to follow the OS. */
export function themeAttribute(choice) {
  return choice === "light" || choice === "dark" ? choice : null;
}

/**
 * Every colour a canvas draws with. `palette[i]` is a track hue (trackHues in
 * paint.js): { fill: clip body, wave: waveform bars, ink: clip outline,
 * label: clip name }. Index MUSIC_HUE is music's role colour.
 */
export function readTheme(
  element = globalThis.document?.documentElement,
  computed = (node) => getComputedStyle(node),
) {
  const style = computed(element);
  const get = (name) => style.getPropertyValue(name).trim();
  const palette = [];
  for (let i = 0; i <= MUSIC_HUE; i += 1) {
    const name = i < SPEAKER_HUES ? String(i) : "music";
    palette.push({
      fill: get(`--track-${name}-body`),
      wave: get(`--track-${name}-wave`),
      ink: get(`--track-${name}-edge`),
      label: get(`--track-${name}-label`),
    });
  }
  return {
    palette,
    ink: get("--text"),
    muted: get("--text-secondary"),
    rule: get("--border-subtle"),
    panel: get("--surface-panel"),
    laneCurrent: get("--surface-lane-current"),
    accent: get("--accent"),
    playhead: get("--playhead"),
    selection: get("--selection-outline"),
    range: get("--selection-range"),
    gain: get("--gain-line"),
    automation: get("--automation-line"),
    hatch: get("--muted-hatch"),
    rulerText: get("--ruler-text"),
    rulerTick: get("--ruler-tick"),
    font: get("--font-ui") || "system-ui, sans-serif",
    mono: get("--font-mono") || "ui-monospace, monospace",
  };
}
