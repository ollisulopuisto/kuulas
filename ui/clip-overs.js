// Where a waveform clips after gain (WP57). Pure, no DOM. The JS twin of
// src/kuulas/clip_overs.py (shared cases: ui/tests/fixtures/gain-overs-cases.json).

/**
 * -0.1 dBFS: a peak above it counts as clipping. A future setting (default
 * stays here); the painter and the tooltip both take it from this constant.
 */
export const CLIP_LIMIT_DB = -0.1;

function checkGain(gainDb) {
  if (!Number.isFinite(gainDb)) throw new RangeError(`gain_db (${gainDb}) must be finite`);
}

/** Runs `[first, last]` (inclusive) of consecutive peak pairs over the limit after `gainDb`. */
export function overs(peaks, gainDb, limitDb = CLIP_LIMIT_DB) {
  checkGain(gainDb);
  if (limitDb > 0) throw new RangeError(`limit_db (${limitDb}) must be <= 0`);
  const gain = 10 ** (gainDb / 20);
  const limit = 10 ** (limitDb / 20);
  const runs = [];
  let start = null;
  peaks.forEach(([low, high], index) => {
    const over = Math.max(Math.abs(low), Math.abs(high)) * gain > limit;
    if (over) {
      if (start === null) start = index;
    } else if (start !== null) {
      runs.push([start, index - 1]);
      start = null;
    }
  });
  if (start !== null) runs.push([start, peaks.length - 1]);
  return runs;
}

/** The largest level above full scale in dB after `gainDb`, or 0. */
export function maxOverDb(peaks, gainDb) {
  checkGain(gainDb);
  const gain = 10 ** (gainDb / 20);
  let max = 0;
  for (const [low, high] of peaks)
    max = Math.max(max, Math.max(Math.abs(low), Math.abs(high)) * gain);
  if (max <= 0) return 0;
  return Math.max(0, 20 * Math.log10(max));
}

/**
 * The same judgement for drawn columns, where the gain differs per column (an
 * envelope). `data` is min/max pairs per column, `dbPerColumn` the total gain of
 * each. Returns `over` (Uint8Array, 1 where the column's peak after gain is
 * above the limit) and `maxOver` (dB above full scale of the loudest, else 0).
 */
export function columnOvers(data, dbPerColumn, limitDb = CLIP_LIMIT_DB) {
  const count = dbPerColumn.length;
  const over = new Uint8Array(count);
  const limit = 10 ** (limitDb / 20);
  let max = 0;
  let lastDb = Number.NaN;
  let gain = 1;
  for (let column = 0; column < count; column += 1) {
    const db = dbPerColumn[column];
    if (db !== lastDb) {
      gain = 10 ** (db / 20);
      lastDb = db;
    }
    const level = Math.max(Math.abs(data[2 * column]), Math.abs(data[2 * column + 1])) * gain;
    if (level > limit) over[column] = 1;
    if (level > max) max = level;
  }
  return { over, maxOver: max > 1 ? 20 * Math.log10(max) : 0 };
}
