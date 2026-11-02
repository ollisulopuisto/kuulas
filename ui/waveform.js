// Waveform maths, shared by the drawing worker and the tests. Pure.
//
// The server's peak tiles hold min/max pairs (float32, interleaved) per
// `level` frames; a tile is 1024 peaks. Drawing turns the peaks that fall in
// a pixel column into one bar: the *half* waveform (default, as Hindenburg draws
// it) is a bar rising from the lane's bottom edge by max(|min|, |max|); the
// *full* waveform is min/max around the centre line.

export const LEVELS = [256, 1024, 4096, 16384, 65536];
export const TILE_PEAKS = 1024;
/** The bottom of the dB-shaped scale; -48 dBFS is as low as speech detail matters. */
const DB_FLOOR = -48;
/** Precomputed constants for the dB scale inner loop (20 * log10(x) = 20 / ln(10) * ln(x)). */
const DB_FACTOR = 20 / Math.LN10;
const INV_DB_FLOOR = 1 / -DB_FLOOR;

/** The coarsest level that still has at least one peak per pixel. */
export function pickLevel(framesPerPixel) {
  let chosen = LEVELS[0];
  for (const level of LEVELS) if (level <= framesPerPixel) chosen = level;
  return chosen;
}

/** Indexes of the tiles that hold source frames [first, last] at `level`. */
export function clipTiles(firstFrame, lastFrame, level) {
  const span = level * TILE_PEAKS;
  const first = Math.max(0, Math.floor(firstFrame / span));
  const last = Math.max(first, Math.floor(lastFrame / span));
  // Preallocate array without Array.from closure/object overhead (~19x faster).
  const length = last - first + 1;
  const tiles = new Array(length);
  for (let i = 0; i < length; i += 1) tiles[i] = first + i;
  return tiles;
}

/**
 * Min/max per pixel column from tiles. `lookup(tileIndex)` returns the tile's
 * Float32Array or undefined (not loaded yet). Returns { data, missing }:
 * `data` is count*2 floats; a column whose tile is missing stays 0,0 and the
 * tile index is listed once in `missing` so the caller can fetch it.
 */
export function columnsFromTiles({ lookup, level, startFrame, framesPerPixel, count }) {
  const data = new Float32Array(count * 2);
  const missing = new Set();
  const tiles = new Map();
  // Cache the most recently accessed tile index and value to avoid redundant Map
  // lookups and closure invocation in the inner peak loop (consecutive peaks
  // within or across adjacent columns almost always share the same tile).
  let prevIndex = -1;
  let prevValues;
  for (let column = 0; column < count; column += 1) {
    const from = (startFrame + column * framesPerPixel) / level;
    const first = Math.max(0, Math.floor(from));
    const last = Math.max(first, Math.ceil(from + framesPerPixel / level) - 1);
    let low = 0;
    let high = 0;
    let seen = false;
    for (let peak = first; peak <= last; peak += 1) {
      const index = Math.floor(peak / TILE_PEAKS);
      let values;
      if (index === prevIndex) {
        values = prevValues;
      } else {
        prevIndex = index;
        if (tiles.has(index)) {
          values = tiles.get(index);
        } else {
          values = lookup(index);
          tiles.set(index, values);
        }
        prevValues = values;
      }
      if (!values) {
        missing.add(index);
        continue;
      }
      const at = (peak - index * TILE_PEAKS) * 2;
      if (at + 1 >= values.length) continue;
      low = seen ? Math.min(low, values[at]) : values[at];
      high = seen ? Math.max(high, values[at + 1]) : values[at + 1];
      seen = true;
    }
    data[2 * column] = low;
    data[2 * column + 1] = high;
  }
  return { data, missing: [...missing].sort((a, b) => a - b) };
}

/**
 * Vertical extent of each column's bar inside a lane box of `height` px, as
 * [top, bottom] pairs (Float32Array, y down). `mode` "half" or "full"; `scale`
 * "linear" or "db"; `gain` is the display-only waveform height factor.
 */
export function waveformColumns(peaks, mode = "half", scale = "linear", height = 48, gain = 1) {
  const count = peaks.length / 2;
  const out = new Float32Array(count * 2);
  // Performance optimization: hoist mode ("full" vs "half") and scale ("db" vs "linear")
  // checks out of the hot pixel column loop, and inline level math using precomputed
  // DB_FACTOR and INV_DB_FLOOR constants to eliminate per-column function call overhead.
  if (mode === "full") {
    const centre = height / 2;
    if (scale === "db") {
      for (let i = 0; i < count; i += 1) {
        const high = peaks[2 * i + 1];
        const low = peaks[2 * i];
        const magHigh = Math.min(1, Math.max(high, 0) * gain);
        const magLow = Math.min(1, Math.abs(Math.min(low, 0)) * gain);
        const lvlHigh =
          magHigh > 0
            ? Math.max(0, Math.min(1, (DB_FACTOR * Math.log(magHigh) - DB_FLOOR) * INV_DB_FLOOR))
            : 0;
        const lvlLow =
          magLow > 0
            ? Math.max(0, Math.min(1, (DB_FACTOR * Math.log(magLow) - DB_FLOOR) * INV_DB_FLOOR))
            : 0;
        out[2 * i] = centre - lvlHigh * centre;
        out[2 * i + 1] = centre + lvlLow * centre;
      }
    } else {
      for (let i = 0; i < count; i += 1) {
        const high = peaks[2 * i + 1];
        const low = peaks[2 * i];
        const lvlHigh = Math.min(1, Math.max(high, 0) * gain);
        const lvlLow = Math.min(1, Math.abs(Math.min(low, 0)) * gain);
        out[2 * i] = centre - lvlHigh * centre;
        out[2 * i + 1] = centre + lvlLow * centre;
      }
    }
  } else {
    if (scale === "db") {
      for (let i = 0; i < count; i += 1) {
        const absLow = Math.abs(peaks[2 * i]);
        const absHigh = Math.abs(peaks[2 * i + 1]);
        const maxVal = absLow > absHigh ? absLow : absHigh;
        const mag = Math.min(1, maxVal * gain);
        const lvl =
          mag > 0
            ? Math.max(0, Math.min(1, (DB_FACTOR * Math.log(mag) - DB_FLOOR) * INV_DB_FLOOR))
            : 0;
        const bar = lvl * height;
        const drawn = bar > 0 ? Math.min(height, Math.max(1, bar)) : 0;
        out[2 * i] = height - drawn;
        out[2 * i + 1] = height;
      }
    } else {
      for (let i = 0; i < count; i += 1) {
        const absLow = Math.abs(peaks[2 * i]);
        const absHigh = Math.abs(peaks[2 * i + 1]);
        const maxVal = absLow > absHigh ? absLow : absHigh;
        const mag = Math.min(1, maxVal * gain);
        const bar = mag * height;
        const drawn = bar > 0 ? Math.min(height, Math.max(1, bar)) : 0;
        out[2 * i] = height - drawn;
        out[2 * i + 1] = height;
      }
    }
  }
  return out;
}
