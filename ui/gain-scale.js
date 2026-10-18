// Waveform scale from clip, track and envelope gains (WP57). Pure, no DOM.
// The JS twin of src/kuulas/gain_scale.py; ui/tests/fixtures/gain-overs-cases.json
// is read by both test suites, so they cannot drift apart.

/** A waveform never grows past 32x (+30 dB) however loud the gains: the lane has a ceiling. */
export const MAX_WAVE_SCALE = 32;

/**
 * Clip + track + envelope gain in dB; null or undefined count as 0. -Infinity
 * (silence) propagates; NaN and +Infinity throw.
 */
export function totalGainDb(clipDb, trackDb, envelopeDb = 0) {
  let total = 0;
  for (const value of [clipDb, trackDb, envelopeDb]) {
    if (value === null || value === undefined) continue;
    if (Number.isNaN(value) || value === Number.POSITIVE_INFINITY)
      throw new RangeError(`gain value (${value}) must be finite or -inf`);
    total += value;
  }
  return total;
}

/** 10^(db/20) capped at `max`; -Infinity maps to 0 (silence). */
export function waveformScale(db, max = MAX_WAVE_SCALE) {
  if (db === Number.NEGATIVE_INFINITY) return 0;
  return Math.min(10 ** (db / 20), max);
}

/**
 * The envelope's dB at `frame` by linear interpolation over sorted
 * `[frame, db]` points; flat before the first and after the last; no points
 * gives 0. Binary search, so a whole lane of columns stays cheap.
 */
export function envelopeDbAt(points, frame) {
  if (!points || points.length === 0) return 0;
  const last = points.length - 1;
  if (frame <= points[0][0]) return points[0][1];
  if (frame >= points[last][0]) return points[last][1];
  let low = 0;
  let high = last;
  while (high - low > 1) {
    const mid = (low + high) >> 1;
    if (points[mid][0] <= frame) low = mid;
    else high = mid;
  }
  const [f0, db0] = points[low];
  const [f1, db1] = points[high];
  if (f1 === f0) return db1;
  return db0 + ((db1 - db0) * (frame - f0)) / (f1 - f0);
}

/**
 * Total dB per drawn column: `baseDb` (clip + track) plus the envelope read at
 * the column's centre. `startFrame` is the source frame of the first column
 * (the envelope is in source frames, so it stays with the audio it was drawn on).
 */
export function columnGainsDb(baseDb, envelope, startFrame, framesPerPixel, count) {
  const out = new Float32Array(count);
  if (!envelope || envelope.length === 0) return out.fill(baseDb);
  for (let column = 0; column < count; column += 1) {
    const centre = startFrame + (column + 0.5) * framesPerPixel;
    out[column] = baseDb + envelopeDbAt(envelope, centre);
  }
  return out;
}
