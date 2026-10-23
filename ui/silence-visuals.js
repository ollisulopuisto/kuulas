// The silent-state visual language (docs/design/SILENCE-VISUALS.md), as pure helpers.
// Independent channels, each with one meaning, so they combine without confusion:
//   fill      FILLED waveform = it sounds; OUTLINE only (no fill) = it is silent
//             (a muted clip, a stretch closed by Auto-Silence, or both). The clip body
//             under a silent stretch is toned down a little (--signal-silent-body).
//   lock      a padlock = closed by Auto-Silence (Track.gate); an OPEN padlock = this clip
//             keeps the mic open (Clip.ungated). A muted clip and a gated stretch differ
//             only by the lock.
//   inactive  not part of the current operation (range scope; listening to a render):
//             dim, desaturate or both (a view preference), never used for silence.
//   preview   the Auto-Silence preview: outline in the preview teal with dashed edges.
// Clip borders, handles and the selection are drawn above every silent-state overlay
// (TRACK_LAYERS), so an edge inside a closed stretch is always seen and grabbable.

/**
 * Which of `count` drawn columns (starting at canvas pixel `from`) are silent: 1 = draw the
 * outline only, 0 = filled. `gate` is gatePixelRuns' merged pixel runs [x0, x1, ...]. A
 * muted clip is silent everywhere; a clip that keeps the mic open ignores the gate.
 */
export function silentColumns(count, from, { muted = false, ungated = false, gate = null } = {}) {
  const mask = new Uint8Array(Math.max(0, count));
  if (muted) return mask.fill(1);
  if (ungated || !gate?.length) return mask;
  for (let i = 0; i < gate.length; i += 2) {
    const first = Math.max(gate[i], from) - from;
    const last = Math.min(gate[i + 1], from + count) - from;
    for (let column = first; column < last; column += 1) mask[column] = 1;
  }
  return mask;
}

/** [start, end, ...] column runs where `mask` is 1. */
export function columnRuns(mask) {
  const runs = [];
  let start = -1;
  for (let column = 0; column < mask.length; column += 1) {
    if (mask[column] && start < 0) start = column;
    else if (!mask[column] && start >= 0) {
      runs.push(start, column);
      start = -1;
    }
  }
  if (start >= 0) runs.push(start, mask.length);
  return runs;
}

/**
 * The waveform's min/max envelope over columns [start, end) as one closed polygon, flat
 * [x, y, x, y, ...] relative to the body's top-left: the top edge left to right through the
 * column centres (plus the run's two ends), then the bottom edge back. `bars` are
 * waveformColumns' [top, bottom] pairs; y is clamped half a pixel inside the body of
 * `height` so a 1 px stroke never covers the clip's border. Stroked, not filled: the
 * "outline only" of a silent stretch. Two points per column, so a 45-minute view at full
 * width costs one path of a few thousand points.
 */
export function envelopeOutline(bars, start, end, height) {
  const clampY = (y) => Math.min(height - 0.5, Math.max(0.5, y));
  const n = end - start;
  const out = new Float32Array((n + 2) * 4);
  let i = 0;
  const push = (x, y) => {
    out[i++] = x;
    out[i++] = clampY(y);
  };
  push(start, bars[2 * start]);
  for (let column = start; column < end; column += 1) push(column + 0.5, bars[2 * column]);
  push(end, bars[2 * (end - 1)]);
  push(end, bars[2 * (end - 1) + 1]);
  for (let column = end - 1; column >= start; column -= 1) push(column + 0.5, bars[2 * column + 1]);
  push(start, bars[2 * start + 1]);
  return out;
}

/**
 * Where the lock icons of the closed stretches go: one per run (gatePixelRuns, already
 * clipped to the view, so its x0 is the left edge of the VISIBLE part), `pad` px in from that
 * edge. `blocked` is a list of [x0, x1] spans the icon must not cover (clip edge zones, fade
 * handles, clip names); the icon slides right past them. A run with no room left for the
 * icon plus padding gets none: the outline alone says silent there. Returns the x of each.
 */
export function lockSpots(runs, { iconPx, pad, blocked = [] }) {
  const spans = [...blocked].sort((a, b) => a[0] - b[0]);
  const spots = [];
  for (let i = 0; i < runs.length; i += 2) {
    let x = runs[i] + pad;
    for (const [b0, b1] of spans) {
      if (b1 < x) continue;
      if (b0 > x + iconPx) break;
      x = b1 + 1;
    }
    if (x + iconPx + pad <= runs[i + 1]) spots.push(x);
  }
  return spots;
}

/**
 * The strength of the outline-only waveform of a silent stretch: full for a muted clip (your
 * decision), dimmed for a stretch Auto-Silence closed (the machine's, owner 2026-10-23), so
 * the two read apart and a closed stretch does not shout. Contrast at this strength is not
 * measured (silence-tokens.test.js checks the full outline).
 */
export function silentOutlineAlpha({ muted }) {
  return muted ? 1 : GATED_OUTLINE_ALPHA;
}
const GATED_OUTLINE_ALPHA = 0.6;

/**
 * How far below the lane's top the closed-stretch padlock sits. A lane with a name strip
 * (36 px and up) puts it under the strip, and under the words row when that is shown: the
 * name is as wide as the clip allows, so a lock in the strip was painted over (owner,
 * 2026-10-23). Null when it would not fit under them: the outline alone says silent.
 */
export function lockTop(rowHeight, { label, words, icon, wordsShown }) {
  if (rowHeight < 36) return 5;
  const top = 2 + label + 4 + (wordsShown ? words + 2 : 0) + 3;
  return top + icon + 3 <= rowHeight - 2 ? top : null;
}

/**
 * The x of the open padlock of a clip that keeps the mic open: `gap` px after the clip name
 * (`after`, its right end), or null when it would reach `limit` (the clip's right edge zone,
 * or the badges there).
 */
export function openLockSpot({ after, limit, iconPx, gap }) {
  const x = after + gap;
  return x + iconPx <= limit ? x : null;
}

/**
 * The pseudo-borders of the closed stretches (owner, 2026-10-21: a stretch should read as its
 * own piece): the x of a 1 px dashed line at each end of every run, on the run's own first and
 * last pixel. Not a clip border: dashed, in the lock colour, no handles, not draggable (hitTest
 * knows nothing of them). An end the view cuts off is no edge; an end within 2 px of a real
 * clip edge (`clipEdges`) is left to the real border, drawn above; a run under 4 px wide gets
 * no lines (the outline alone says silent there).
 */
/** The dash of a stretch edge: short, so it never reads as a clip's solid border. */
export const STRETCH_EDGE_DASH = [3, 3];

export function stretchEdges(runs, { width, clipEdges = [] }) {
  const nearClip = (x) => clipEdges.some((edge) => Math.abs(edge - x) <= 2);
  const out = [];
  for (let i = 0; i < runs.length; i += 2) {
    const [x0, x1] = [runs[i], runs[i + 1]];
    if (x1 - x0 < 4) continue;
    if (x0 > 0 && !nearClip(x0)) out.push(x0);
    if (x1 < width && !nearClip(x1)) out.push(x1 - 1);
  }
  return out;
}

/** The overlays that mark silence on the timeline's overlay canvas (the waveform layer's
 *  outline and body tone are under the whole overlay anyway). */
export const SILENT_OVERLAY_LAYERS = ["preview", "stretchEdges", "locks"];

/**
 * The order timeline.js draws a track's lane in. "clips" is each clip's chrome: border,
 * crossfades, name (with the open padlock), words, gain line, fade handles, sibling marks and
 * the selection outline, all above the silent-state overlays, so borders and handles are
 * never buried (owner, 2026-10-21: the hatch hid the borders of gated clips).
 */
export const TRACK_LAYERS = [
  ...SILENT_OVERLAY_LAYERS,
  "clips",
  "placeholders",
  "collateral",
  "candidates",
  "seams",
  "automation",
  "previewLabel",
];

/** The legend the Auto-Silence panel shows: one line per state, in the language's order. */
export const SILENCE_LEGEND_TITLE = "ui.silence.legend_title";
export const SILENCE_LEGEND = [
  { state: "filled", key: "ui.silence.legend.filled" },
  { state: "outline", key: "ui.silence.legend.outline" },
  { state: "lock", key: "ui.silence.legend.lock", icon: "lock" },
  { state: "edges", key: "ui.silence.legend.edges" },
  { state: "open", key: "ui.silence.legend.open", icon: "unlock" },
  { state: "preview", key: "ui.silence.legend.preview" },
  { state: "inactive", key: "ui.silence.legend.inactive" },
  { state: "group", key: "ui.silence.legend.group" },
];

// -- the inactive style ------------------------------------------------------------------

/** How a lane outside the current operation looks (a view preference). */
export const INACTIVE_STYLES = ["both", "desaturate", "dim"];
/**
 * Default: desaturate plus a light veil. Desaturating keeps the waveform readable (its
 * luminance, so its contrast, is unchanged) while the lost hue says "not in play"; a light
 * veil adds the step back in depth that grey alone lacks next to grey-ish hues (music, sand).
 */
export const DEFAULT_INACTIVE_STYLE = "both";
/** The full veil of the "dim" variant (WP83's DIM_ALPHA). */
const DIM_VEIL = 0.72;
/** The light veil of "both": well under half the full one. */
const LIGHT_VEIL = 0.3;

export const inactiveStyleChoice = (stored) =>
  INACTIVE_STYLES.includes(stored) ? stored : DEFAULT_INACTIVE_STYLE;

/** { veil: alpha of the panel-coloured veil (0 = none), desaturate: use the grey palette }. */
export function inactiveLook(style) {
  const choice = inactiveStyleChoice(style);
  if (choice === "dim") return { veil: DIM_VEIL, desaturate: false };
  if (choice === "desaturate") return { veil: 0, desaturate: true };
  return { veil: LIGHT_VEIL, desaturate: true };
}

const RGB = "rgb";
const linear = (v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const gamma = (v) => (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055);

/** The grey of the same relative luminance as r, g, b (0..255): WCAG contrast is unchanged. */
function greyOf(r, g, b) {
  const y = 0.2126 * linear(r / 255) + 0.7152 * linear(g / 255) + 0.0722 * linear(b / 255);
  return Math.round(gamma(y) * 255);
}

/**
 * A CSS colour (#rrggbb, rgb(r g b / a) or rgba(r, g, b, a)) as the grey of the same
 * luminance; anything else is returned unchanged. Computed once per theme (theme.js), never
 * per frame, so the desaturated look costs nothing to draw.
 */
export function desaturateColour(css) {
  const text = String(css ?? "").trim();
  const hex = text.match(/^#([0-9a-f]{6})$/i);
  if (hex) {
    const [r, g, b] = [0, 2, 4].map((i) => Number.parseInt(hex[1].slice(i, i + 2), 16));
    const v = greyOf(r, g, b).toString(16).padStart(2, "0");
    return `#${v}${v}${v}`;
  }
  const fn = text.match(
    /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)\s*(?:[/,]\s*([\d.]+%?))?\s*\)$/i,
  );
  if (fn) {
    const v = greyOf(Number(fn[1]), Number(fn[2]), Number(fn[3]));
    // Built from parts: a derived colour, not a literal (tokens.test.js scans for literals).
    const grey = `${v} ${v} ${v}`;
    return fn[4] === undefined ? `${RGB}(${grey})` : `${RGB}(${grey} / ${fn[4]})`;
  }
  return text;
}

/** Every colour of every palette entry desaturated (theme.js keeps it beside the palette). */
export function desaturatePalette(palette) {
  return palette.map((entry) =>
    Object.fromEntries(Object.entries(entry).map(([key, value]) => [key, desaturateColour(value)])),
  );
}
