// Colours for the canvases. The tokens are named in grammar.js and defined in
// tokens.css; readTheme resolves them ONCE per theme change into a plain
// object the timeline, the overview and the waveform worker draw with. Call
// it again (timeline.refreshTheme) when the theme or the OS preference
// changes; never per frame. Spec: docs/design/GUI-DESIGN.md, "Themes".
import { resolvePalette } from "./grammar.js";

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

/** Two densities (owner, 2026-10-18): comfortable (the roomy default) and compact. */
export const DENSITIES = ["comfortable", "compact"];

/** The value of <html data-density>, or null for the default (comfortable). */
export function densityAttribute(choice) {
  return choice === "compact" ? "compact" : null;
}

/**
 * The canvas palette. `palette[i]` is a track hue (trackHues in paint.js):
 * { fill: clip body, fillAlt: the other file's body tone (zebra), wave:
 * waveform bars, ink: clip outline, label: clip name }. The flat names below
 * are what timeline.js and overview.js use; `resolved` is the full registry
 * palette for anything newer.
 */
export function readTheme(
  element = globalThis.document?.documentElement,
  computed = (node) => getComputedStyle(node),
) {
  const style = computed(element);
  const p = resolvePalette((name) => style.getPropertyValue(name));
  return {
    resolved: p,
    palette: p.tracks.map((t) => ({
      fill: t.body,
      fillAlt: t.bodyAlt,
      wave: t.wave,
      ink: t.edge,
      label: t.label,
    })),
    busBands: p.buses.map((b) => b.band),
    busSpines: p.buses.map((b) => b.spine),
    ink: p.surfaces.text,
    muted: p.surfaces.textSecondary,
    rule: p.surfaces.borderSubtle,
    border: p.surfaces.border,
    panel: p.surfaces.surfacePanel,
    laneCurrent: p.surfaces.surfaceLaneCurrent,
    accent: p.surfaces.accent,
    accentText: p.surfaces.accentText,
    playhead: p.marks.playhead,
    playStart: p.marks.playStart,
    range: p.marks.selectionRange,
    gain: p.marks.gainLine,
    automation: p.marks.automationLine,
    rulerText: p.marks.rulerText,
    rulerTick: p.marks.rulerTick,
    selection: p.signals.selected,
    hatch: p.signals.mutedHatch,
    clipping: p.signals.clipping,
    seam: p.signals.seam,
    sibling: p.signals.sibling,
    collateral: p.signals.collateral,
    collateralFill: p.signals.collateralFill,
    fileMark: p.signals.fileMark,
    fileMarkText: p.signals.fileMarkText,
    mutedOpacity: p.numbers.mutedOpacity,
    note: p.signals.note,
    candidate: p.signals.candidate,
    candidateFill: p.signals.candidateFill,
    gate: p.signals.gate,
    placeholder: p.signals.placeholder,
    gateOpacity: p.numbers.gateOpacity,
    font: p.font,
    mono: p.mono,
  };
}
