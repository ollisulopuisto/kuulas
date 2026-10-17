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
  return Array.from({ length: last - first + 1 }, (_, i) => first + i);
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
  const tile = (index) => {
    if (!tiles.has(index)) tiles.set(index, lookup(index));
    return tiles.get(index);
  };
  for (let column = 0; column < count; column += 1) {
    const from = (startFrame + column * framesPerPixel) / level;
    const first = Math.max(0, Math.floor(from));
    const last = Math.max(first, Math.ceil(from + framesPerPixel / level) - 1);
    let low = 0;
    let high = 0;
    let seen = false;
    for (let peak = first; peak <= last; peak += 1) {
      const index = Math.floor(peak / TILE_PEAKS);
      const values = tile(index);
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

function level(value, scale, gain) {
  const magnitude = Math.min(1, Math.abs(value) * gain);
  if (magnitude <= 0) return 0;
  if (scale !== "db") return magnitude;
  return Math.max(0, Math.min(1, (20 * Math.log10(magnitude) - DB_FLOOR) / -DB_FLOOR));
}

/**
 * Vertical extent of each column's bar inside a lane box of `height` px, as
 * [top, bottom] pairs (Float32Array, y down). `mode` "half" or "full"; `scale`
 * "linear" or "db"; `gain` is the display-only waveform height factor.
 */
export function waveformColumns(peaks, mode = "half", scale = "linear", height = 48, gain = 1) {
  const count = peaks.length / 2;
  const out = new Float32Array(count * 2);
  for (let i = 0; i < count; i += 1) {
    const low = peaks[2 * i];
    const high = peaks[2 * i + 1];
    if (mode === "full") {
      const centre = height / 2;
      out[2 * i] = centre - level(Math.max(high, 0), scale, gain) * centre;
      out[2 * i + 1] = centre + level(Math.min(low, 0), scale, gain) * centre;
    } else {
      const bar = level(Math.max(Math.abs(low), Math.abs(high)), scale, gain) * height;
      const drawn = bar > 0 ? Math.min(height, Math.max(1, bar)) : 0;
      out[2 * i] = height - drawn;
      out[2 * i + 1] = height;
    }
  }
  return out;
}
