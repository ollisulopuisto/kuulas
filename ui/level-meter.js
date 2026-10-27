import { t } from "./i18n.js";

// The status-bar meter retains its graphical bar and reference scale at rest.
// The bar and numeric readout use the shared three-second K-weighted LUFS value;
// peak samples are used only for the independent clipping warning. Legacy peak
// arithmetic below is also used by tests and remains separate from the LUFS scale.

/** The scale: -60 dBFS (empty) to 0 dBFS (full), linear in dB. */
export const METER_MIN_DB = -60;
export const METER_MAX_DB = 0;
/** Reference marks on the scale. */
export const TICKS_DB = [-18, -6];
/** Green below -6, amber from -6, red from -1 (hot enough to be worth a look). */
export const WARN_DB = -6;
export const HOT_DB = -1;
/** How fast a bar falls back, dB per second; a rise is immediate. The server's peak-hold
 * tick falls on its own, slower (meter.py). */
export const RELEASE_DB_PER_S = 24;

const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

/** x in 0..width for a level in dBFS; anything not a number, or below the floor, is 0. */
export function dbToX(db, width) {
  if (!Number.isFinite(db)) return 0;
  const clamped = clamp(db, METER_MIN_DB, METER_MAX_DB);
  return ((clamped - METER_MIN_DB) / (METER_MAX_DB - METER_MIN_DB)) * width;
}

export function zoneOf(db) {
  if (db >= HOT_DB) return "hot";
  if (db >= WARN_DB) return "warn";
  return "ok";
}

/** The coloured pieces of a bar of `db`: `[{ zone, from, to }]` in pixels, meeting end to end. */
export function zoneSegments(db, width) {
  const end = dbToX(db, width);
  if (end <= 0) return [];
  const edges = [
    ["ok", 0],
    ["warn", dbToX(WARN_DB, width)],
    ["hot", dbToX(HOT_DB, width)],
  ];
  const out = [];
  edges.forEach(([zone, from], i) => {
    const to = i + 1 < edges.length ? Math.min(edges[i + 1][1], end) : end;
    if (to > from) out.push({ zone, from, to });
  });
  return out;
}

/** Full scale or beyond on either channel. */
export function isClipping({ l, r }) {
  return l >= 0 || r >= 0;
}

export const initialMeter = () => ({
  l: METER_MIN_DB,
  r: METER_MIN_DB,
  holdL: METER_MIN_DB,
  holdR: METER_MIN_DB,
  clip: false,
});

const FLOOR_FRAME_DB = -89;
const isFloorFrame = (m) => m.l <= FLOOR_FRAME_DB && m.r <= FLOOR_FRAME_DB;

const fall = (shown, now, seconds) =>
  Math.max(now, shown - RELEASE_DB_PER_S * seconds, METER_MIN_DB);

/**
 * The display state after a frame from the server, `seconds` after the previous one: a louder
 * level shows at once, a quieter one falls at RELEASE_DB_PER_S (never below what plays now); the
 * hold ticks are the server's; a clip latches until clearClip(). The floor frame the server
 * sends when playback stops empties the bars at once and leaves a latched clip.
 */
export function advance(state, message, seconds) {
  if (isFloorFrame(message)) {
    return { ...initialMeter(), clip: state.clip };
  }
  return {
    l: Math.max(message.l, fall(state.l, message.l, seconds)),
    r: Math.max(message.r, fall(state.r, message.r, seconds)),
    holdL: Math.max(message.hold_l, METER_MIN_DB),
    holdR: Math.max(message.hold_r, METER_MIN_DB),
    clip: state.clip || isClipping(message),
  };
}

export const clearClip = (state) => ({ ...state, clip: false });

/** The bars only while playing; the clip light also while stopped, until it is clicked. */
export function meterVisible(state, meter) {
  return { bars: Boolean(state.playing), clip: Boolean(meter.clip) };
}

/** Three-second K-weighted loudness, with peak clipping kept separately. */
export const LUFS_TICKS = [-23, -16];
export const lufsToX = (value, width) =>
  Number.isFinite(value) ? ((clamp(value, -50, -8) + 50) / 42) * width : 0;
export const shortTermLevel = (message) =>
  Number.isFinite(message.short_term) ? message.short_term : null;

export function createLevelMeter({ root, bars, clipButton, onClipClear = () => {} }) {
  const fill = bars.querySelector(".lm-fill");
  const readout = root.querySelector(".lm-readout");
  let state = initialMeter();
  let loudness = null;

  function paint() {
    bars.hidden = false;
    readout.hidden = false;
    clipButton.hidden = !state.clip;
    root.hidden = false;
    fill.style.width = `${lufsToX(loudness, bars.clientWidth || 140)}px`;
    fill.dataset.zone = loudness !== null && loudness > -16 ? "warn" : "ok";
    readout.textContent =
      loudness === null || loudness <= -89
        ? t("ui.meter.pending")
        : t("ui.meter.value", { value: loudness.toFixed(1) });
    for (const tick of bars.querySelectorAll(".lm-tick")) {
      tick.style.left = `${lufsToX(Number(tick.dataset.lufs), 100)}%`;
    }
  }

  clipButton.addEventListener("click", () => {
    state = clearClip(state);
    paint();
    onClipClear();
  });

  paint();

  return {
    frame(message) {
      state = advance(state, message, 0);
      loudness = shortTermLevel(message);
      paint();
    },
    playing(on) {
      if (!on) {
        state = advance(state, { l: -90, r: -90, hold_l: -90, hold_r: -90 }, 0);
        loudness = null;
      }
      paint();
    },
  };
}
