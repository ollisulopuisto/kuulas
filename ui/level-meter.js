// The live level meter in the status bar (owner, 2026-10-19: VU meters, to get tracks and
// buses to unity gain before export). It shows what plays now: peak per channel in dBFS from
// the live channel (`{ type: "meter", meter: { l, r, hold_l, hold_r } }`, about 15 a second
// while playing). That is not the loudness readout in a track header, which is the analysed
// integrated LUFS. The arithmetic here is pure; createLevelMeter() only moves DOM styles.

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

/**
 * Wire the meter's DOM (index.html `#level-meter`). `bars` hold two `.lm-row`s, each with a
 * `.lm-fill` per zone and a `.lm-hold`; `clipButton` is the red light. Redrawn on each frame
 * only (about 15 a second), by setting a handful of styles: no layout is read.
 */
export function createLevelMeter({ root, bars, clipButton, onClipClear = () => {} }) {
  const rows = [...bars.querySelectorAll(".lm-row")];
  const width = () => bars.clientWidth || 140;
  let state = initialMeter();
  let lastAt = null;

  function paint(playing) {
    const w = width();
    const shown = meterVisible({ playing }, state);
    bars.hidden = !shown.bars;
    clipButton.hidden = !shown.clip;
    root.hidden = !shown.bars && !shown.clip;
    if (!shown.bars) return;
    [
      [state.l, state.holdL],
      [state.r, state.holdR],
    ].forEach(([level, hold], i) => {
      const row = rows[i];
      const fills = row.querySelectorAll(".lm-fill");
      const segments = zoneSegments(level, w);
      fills.forEach((fill) => {
        const seg = segments.find((s) => s.zone === fill.dataset.zone);
        fill.style.left = `${seg ? seg.from : 0}px`;
        fill.style.width = `${seg ? seg.to - seg.from : 0}px`;
      });
      const tick = row.querySelector(".lm-hold");
      tick.hidden = dbToX(hold, w) <= 0;
      tick.style.left = `${Math.max(0, dbToX(hold, w) - 1)}px`;
      tick.dataset.zone = zoneOf(hold);
    });
  }

  clipButton.addEventListener("click", () => {
    state = clearClip(state);
    paint(false);
    onClipClear();
  });

  return {
    /** A frame from the live channel. */
    frame(message, now = performance.now()) {
      const seconds = lastAt === null ? 0 : (now - lastAt) / 1000;
      lastAt = now;
      state = advance(state, message, seconds);
      paint(true);
    },
    /** Playback stopped (or started): the bars leave (or wait for the first frame). */
    playing(on) {
      if (!on) {
        state = advance(state, { l: -90, r: -90, hold_l: -90, hold_r: -90 }, 0);
        lastAt = null;
      }
      paint(on);
    },
  };
}
